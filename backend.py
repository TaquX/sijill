"""
backend.py — Sijill processing engine.

Everything that is not UI lives here, so it can be used by the Streamlit app
(app.py), by the REST API (api.py), and by the tests:

- Reading receipts with Gemma 4 (via the Gemini API), with JSON repair + retry
- Cleaning the model output (Turkish decimals, dates, categories)
- Verifying totals and detecting duplicate receipts
- Currency conversion with live rates (offline fallback)
- Summaries, a printable monthly report, and Q&A over the data
- Saving receipts to disk so a page refresh doesn't lose them

License: MIT
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
import time
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "gemma-4-31b-it"

# Category names are the stored values (the app's tables and charts use them).
CATEGORIES = ["طعام وبقالة", "مطاعم ومقاهي", "مواصلات", "فواتير وخدمات",
              "صحة وأدوية", "ملابس", "إلكترونيات", "تعليم", "أخرى"]
OTHER = "أخرى"

LANG_NAMES = {"ar": "Arabic", "tr": "Turkish", "en": "English"}

# ---------------------------------------------------------------------------
# Gemma client
# ---------------------------------------------------------------------------


def get_client(api_key: str):
    """Create a Gemini API client (Gemma models are served through it)."""
    from google import genai  # imported lazily so tests run without network

    if not api_key:
        raise ValueError("Missing Gemini API key")
    return genai.Client(api_key=api_key)


def list_gemma_models(client) -> list[str]:
    return [m.name for m in client.models.list() if "gemma" in m.name.lower()]


def _generate(client, model: str, contents) -> str:
    resp = client.models.generate_content(model=model, contents=contents)
    text = getattr(resp, "text", None)
    if not text:
        raise RuntimeError("Empty response from the model")
    return text


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
MAX_SIDE = 1600  # px — big enough for receipt text, small enough to be fast


def prepare_image(image_bytes: bytes, mime: str | None = None) -> tuple[bytes, str]:
    """Fix phone rotation, shrink large photos and re-encode as JPEG.
    Falls back to the original bytes if Pillow can't open the file."""
    try:
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=88)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, mime or "image/jpeg"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def to_number(value: Any) -> float | None:
    """Turn model output into a float. Handles Turkish formats:
    '12,50' -> 12.5, '1.234,56' -> 1234.56, '₺ 45' -> 45.0, '1,234.56' -> 1234.56"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^\d,.\-]", "", str(value))
    if not s or s in {"-", ".", ","}:
        return None
    if "," in s and "." in s:
        # whichever separator comes last is the decimal one
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Turkish receipts: a lone comma is the decimal separator ('12,50')
        if s.count(",") > 1:
            head, _, tail = s.rpartition(",")
            s = head.replace(",", "") + "." + tail
        else:
            s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y", "%Y/%m/%d"]


def to_iso_date(value: Any) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", s)
    if m:
        d, mo, y = m.groups()
        y = int(y) + 2000 if len(y) == 2 else int(y)
        try:
            return datetime(y, int(mo), int(d)).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


CURRENCY_ALIASES = {"₺": "TRY", "TL": "TRY", "YTL": "TRY", "$": "USD", "€": "EUR", "£": "GBP"}


def to_currency(value: Any, default: str = "TRY") -> str:
    if not value:
        return default
    s = str(value).strip()
    if s in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[s]
    up = s.upper()
    if up in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[up]
    for sym, code in CURRENCY_ALIASES.items():
        if not sym.isalpha() and sym in s:
            return code
    letters = re.sub(r"[^A-Z]", "", up)
    return letters[:3] if len(letters) >= 3 else default


def extract_json(text: str) -> dict:
    """Find and parse the first JSON object in the model's reply,
    tolerating code fences, extra prose and trailing commas."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        if start == -1:
            raise ValueError("No JSON object in model reply")
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
        if candidate is None:
            candidate = text[start:]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)  # trailing commas
    return json.loads(candidate)


def normalize_receipt(raw: dict) -> dict:
    """Clean one receipt from the model into a predictable shape."""
    items = []
    for it in raw.get("items") or []:
        if not isinstance(it, dict):
            continue
        qty = to_number(it.get("qty"))
        unit = to_number(it.get("unit_price"))
        total = to_number(it.get("total"))
        if total is None and qty is not None and unit is not None:
            total = round(qty * unit, 2)
        items.append({
            "name_original": (it.get("name_original") or it.get("name") or "").strip(),
            "name_translated": (it.get("name_translated") or "").strip(),
            "qty": qty if qty is not None else 1.0,
            "unit_price": unit,
            "total": total,
        })

    total = to_number(raw.get("total"))
    if total is None and items:
        total = round(sum(i["total"] or 0 for i in items), 2)

    category = raw.get("category")
    if category not in CATEGORIES:
        category = OTHER

    return {
        "store_name": (raw.get("store_name") or "").strip() or None,
        "date": to_iso_date(raw.get("date")),
        "currency": to_currency(raw.get("currency")),
        "category": category,
        "items": items,
        "tax": to_number(raw.get("tax")),
        "total": total,
        "notes": (raw.get("notes") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Reading receipts
# ---------------------------------------------------------------------------
EXTRACT_PROMPT = """You are an expert receipt reader. The receipt may be in Turkish, Arabic, or English.
Read the receipt image carefully and return ONLY a valid JSON object, no other text, in this exact schema:

{{
  "store_name": "string",
  "date": "YYYY-MM-DD or null",
  "currency": "TRY / USD / EUR / ...",
  "category": "one of: {cats}",
  "items": [
    {{"name_original": "string", "name_translated": "string in {lang}", "qty": number, "unit_price": number, "total": number}}
  ],
  "tax": number or null,
  "total": number,
  "notes": "short note in {lang}, e.g. payment method or anything unclear"
}}

Rules:
- Use numbers only (no currency symbols). Turkish receipts use comma as decimal separator: 12,50 means 12.50.
- "total" is the final amount paid (TOPLAM / TOP / GENEL TOPLAM), including tax.
- Turkish "KDV" or "TOPKDV" is the tax amount.
- If a value is unreadable, use null. Never invent items that are not on the receipt.
- "category" must be exactly one of the listed categories.
- If the image is not a receipt, return {{"error": "not_a_receipt"}}.
"""

REPAIR_PROMPT = """Your previous answer was not valid JSON. Return ONLY the corrected JSON object,
with no explanation and no code fences. Previous answer:

{previous}"""


class NotAReceiptError(ValueError):
    pass


def read_receipt(client, image_bytes: bytes, mime: str | None = None,
                 lang: str = "ar", model: str = DEFAULT_MODEL, retries: int = 2) -> dict:
    """Image -> cleaned receipt dict. Retries with a JSON-repair prompt if needed."""
    from google.genai import types

    data, mime = prepare_image(image_bytes, mime)
    prompt = EXTRACT_PROMPT.format(cats=", ".join(CATEGORIES), lang=LANG_NAMES.get(lang, "Arabic"))
    image_part = types.Part.from_bytes(data=data, mime_type=mime)

    text = _generate(client, model, [image_part, prompt])
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            raw = extract_json(text)
            if raw.get("error") == "not_a_receipt":
                raise NotAReceiptError("This image does not look like a receipt")
            return normalize_receipt(raw)
        except NotAReceiptError:
            raise
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < retries:
                text = _generate(client, model, REPAIR_PROMPT.format(previous=text[:6000]))
    raise ValueError(f"Could not parse the model's answer: {last_err}")


# ---------------------------------------------------------------------------
# Verification & duplicates
# ---------------------------------------------------------------------------
CHECK_LABELS = {
    "ok": {"ar": "✅ متطابق", "tr": "✅ Tutarlı", "en": "✅ Totals match"},
    "mismatch": {"ar": "⚠️ فرق {diff}", "tr": "⚠️ Fark {diff}", "en": "⚠️ Off by {diff}"},
    "no_total": {"ar": "⚠️ لا يوجد إجمالي", "tr": "⚠️ Toplam yok", "en": "⚠️ No total"},
    "no_items": {"ar": "ℹ️ لا توجد أصناف", "tr": "ℹ️ Ürün yok", "en": "ℹ️ No items"},
}


def verify(receipt: dict) -> dict:
    """Do the item totals add up to the receipt total?
    Returns {"status": ok|mismatch|no_total|no_items, "diff": float}."""
    total = receipt.get("total")
    items = receipt.get("items") or []
    if not total:
        return {"status": "no_total", "diff": 0.0}
    if not items:
        return {"status": "no_items", "diff": 0.0}
    s = sum((i.get("total") or 0) for i in items)
    diff = round(abs(s - total), 2)
    # allow small rounding gaps and receipts that list tax separately
    tax = receipt.get("tax") or 0
    if diff < 1 or diff <= 0.05 * total or (tax and abs(s + tax - total) < 1):
        return {"status": "ok", "diff": diff}
    return {"status": "mismatch", "diff": diff}


def check_label(check: dict, lang: str = "ar") -> str:
    tpl = CHECK_LABELS.get(check["status"], CHECK_LABELS["no_total"]).get(lang) or CHECK_LABELS["no_total"]["en"]
    return tpl.format(diff=f"{check['diff']:.2f}")


def fingerprint(receipt: dict) -> str:
    """Same store + date + total = probably the same receipt scanned twice."""
    key = "|".join([
        (receipt.get("store_name") or "").lower().strip(),
        receipt.get("date") or "",
        f"{receipt.get('total') or 0:.2f}",
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def is_duplicate(receipt: dict, existing: list[dict]) -> bool:
    fp = fingerprint(receipt)
    return any(r.get("id") == fp or fingerprint(r) == fp for r in existing)


def finalize(receipt: dict, source: str = "", lang: str = "ar") -> dict:
    """Attach id, verification and metadata before storing."""
    r = dict(receipt)
    r["id"] = fingerprint(r)
    r["check"] = verify(r)
    r["_check"] = check_label(r["check"], lang)  # display label used by the UI cards
    r["_file"] = source
    r["added_at"] = datetime.now().isoformat(timespec="seconds")
    return r


def relabel(receipts: list[dict], lang: str) -> list[dict]:
    """Re-translate verification labels when the user switches language."""
    for r in receipts:
        r["check"] = verify(r)
        r["_check"] = check_label(r["check"], lang)
    return receipts


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------
# Rough fallback rates (per 1 TRY) used only if the live API is unreachable.
FALLBACK_PER_TRY = {"TRY": 1.0, "USD": 0.024, "EUR": 0.022, "GBP": 0.018, "SAR": 0.09, "AED": 0.088}
_RATES_CACHE: dict[str, tuple[float, dict, bool]] = {}
RATES_TTL = 3600


def get_rates(base: str = "TRY", timeout: float = 5.0) -> tuple[dict, bool]:
    """Exchange rates from `base` to other currencies.
    Returns (rates, live) — live=False means fallback rates were used."""
    base = base.upper()
    cached = _RATES_CACHE.get(base)
    if cached and time.time() - cached[0] < RATES_TTL:
        return cached[1], cached[2]
    try:
        url = f"https://open.er-api.com/v6/latest/{base}"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.load(resp)
        rates = {k.upper(): float(v) for k, v in data["rates"].items()}
        rates[base] = 1.0
        _RATES_CACHE[base] = (time.time(), rates, True)
        return rates, True
    except Exception:
        per_try = FALLBACK_PER_TRY
        if base not in per_try:
            return {base: 1.0}, False
        rates = {k: v / per_try[base] for k, v in per_try.items()}
        return rates, False


def convert(amount: float | None, from_cur: str, to_cur: str, rates_from_target: dict) -> float | None:
    """Convert using rates where rates[X] = units of X per 1 target currency."""
    if amount is None:
        return None
    from_cur, to_cur = (from_cur or "TRY").upper(), to_cur.upper()
    if from_cur == to_cur:
        return float(amount)
    rate = rates_from_target.get(from_cur)
    if not rate:
        return None
    return round(float(amount) / rate, 2)


# ---------------------------------------------------------------------------
# Summaries & report
# ---------------------------------------------------------------------------


def summarize(receipts: list[dict], target: str = "TRY", rates: dict | None = None) -> dict:
    """Totals in one currency, by category, month and store, plus top items."""
    target = target.upper()
    if rates is None:
        rates, _ = get_rates(target)

    by_cat: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    by_store: dict[str, float] = defaultdict(float)
    items_count: dict[str, float] = defaultdict(float)
    total, unconverted = 0.0, 0

    for r in receipts:
        amt = convert(r.get("total"), r.get("currency"), target, rates)
        if amt is None:
            unconverted += 1
            continue
        total += amt
        by_cat[r.get("category") or OTHER] += amt
        by_month[(r.get("date") or "")[:7] or "—"] += amt
        by_store[r.get("store_name") or "—"] += amt
        for it in r.get("items") or []:
            name = it.get("name_translated") or it.get("name_original")
            if name:
                items_count[name] += convert(it.get("total") or 0, r.get("currency"), target, rates) or 0

    def top(d, n=None):
        return dict(sorted(((k, round(v, 2)) for k, v in d.items()), key=lambda kv: -kv[1])[:n])

    n = len(receipts) - unconverted
    return {
        "currency": target,
        "total": round(total, 2),
        "count": len(receipts),
        "average": round(total / n, 2) if n else 0.0,
        "by_category": top(by_cat),
        "by_month": dict(sorted((k, round(v, 2)) for k, v in by_month.items())),
        "by_store": top(by_store, 10),
        "top_items": top(items_count, 10),
        "unconverted": unconverted,
    }


REPORT_TEXT = {
    "ar": {"title": "تقرير المصاريف", "generated": "تاريخ التقرير", "total": "الإجمالي",
           "count": "عدد الإيصالات", "avg": "متوسط الإيصال", "by_cat": "حسب التصنيف",
           "by_month": "حسب الشهر", "receipts": "الإيصالات", "store": "المتجر", "date": "التاريخ",
           "category": "التصنيف", "amount": "المبلغ", "check": "التحقق", "top_stores": "أكثر المتاجر"},
    "tr": {"title": "Harcama Raporu", "generated": "Rapor tarihi", "total": "Toplam",
           "count": "Fiş sayısı", "avg": "Ortalama fiş", "by_cat": "Kategoriye göre",
           "by_month": "Aya göre", "receipts": "Fişler", "store": "Mağaza", "date": "Tarih",
           "category": "Kategori", "amount": "Tutar", "check": "Kontrol", "top_stores": "En çok harcanan mağazalar"},
    "en": {"title": "Expense Report", "generated": "Generated", "total": "Total",
           "count": "Receipts", "avg": "Average receipt", "by_cat": "By category",
           "by_month": "By month", "receipts": "Receipts", "store": "Store", "date": "Date",
           "category": "Category", "amount": "Amount", "check": "Check", "top_stores": "Top stores"},
}


def report_html(receipts: list[dict], summary: dict, lang: str = "ar", title_suffix: str = "") -> str:
    """Self-contained printable HTML report (open in a browser → Print → Save as PDF)."""
    T = REPORT_TEXT.get(lang, REPORT_TEXT["en"])
    cur = html.escape(summary["currency"])
    rtl = lang == "ar"
    esc = html.escape

    def rows(d):
        mx = max(d.values()) if d else 1
        return "".join(
            f'<tr><td>{esc(str(k))}</td><td class="num">{v:,.2f} {cur}</td>'
            f'<td><div class="bar" style="width:{(v / mx * 100) if mx else 0:.0f}%"></div></td></tr>'
            for k, v in d.items()
        )

    receipt_rows = "".join(
        f"<tr><td>{esc(r.get('store_name') or '—')}</td><td>{esc(r.get('date') or '—')}</td>"
        f"<td>{esc(r.get('category') or '')}</td>"
        f"<td class='num'>{(r.get('total') or 0):,.2f} {esc(r.get('currency') or '')}</td>"
        f"<td>{esc(r.get('_check') or '')}</td></tr>"
        for r in sorted(receipts, key=lambda x: x.get("date") or "")
    )

    return f"""<!doctype html>
<html lang="{lang}" dir="{'rtl' if rtl else 'ltr'}"><head><meta charset="utf-8">
<title>{T['title']} {esc(title_suffix)}</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;800&family=Inter:wght@400;700;800&display=swap" rel="stylesheet">
<style>
 body{{font-family:{"'Cairo'" if rtl else "'Inter'"},Tahoma,sans-serif;color:#1F2933;margin:32px;}}
 header{{border-bottom:3px solid #0F766E;padding-bottom:12px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:end}}
 h1{{margin:0;color:#0F766E}} h2{{color:#0F766E;font-size:1.1rem;margin-top:28px}}
 .muted{{color:#6B7280;font-size:.85rem}}
 .kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
 .kpi{{border:1px solid #E8E1D5;border-radius:10px;padding:12px;background:#FFFDF8}}
 .kpi b{{display:block;font-size:1.5rem;direction:ltr;text-align:{'right' if rtl else 'left'}}}
 table{{width:100%;border-collapse:collapse;font-size:.9rem}}
 td,th{{padding:6px 8px;border-bottom:1px solid #EEE;text-align:{'right' if rtl else 'left'}}}
 th{{background:#F1ECE3}} .num{{direction:ltr;white-space:nowrap}}
 .bar{{height:10px;background:#0F766E;border-radius:4px;min-width:2px}}
 @media print{{body{{margin:12mm}} .noprint{{display:none}}}}
</style></head><body>
<header><div><h1>🧾 سجلّ · {T['title']}</h1><div class="muted">{esc(title_suffix)}</div></div>
<div class="muted">{T['generated']}: {datetime.now():%Y-%m-%d %H:%M}</div></header>
<div class="kpis">
 <div class="kpi">{T['total']}<b>{summary['total']:,.2f} {cur}</b></div>
 <div class="kpi">{T['count']}<b>{summary['count']}</b></div>
 <div class="kpi">{T['avg']}<b>{summary['average']:,.2f} {cur}</b></div>
</div>
<h2>{T['by_cat']}</h2><table>{rows(summary['by_category'])}</table>
<h2>{T['by_month']}</h2><table>{rows(summary['by_month'])}</table>
<h2>{T['top_stores']}</h2><table>{rows(summary['by_store'])}</table>
<h2>{T['receipts']}</h2>
<table><tr><th>{T['store']}</th><th>{T['date']}</th><th>{T['category']}</th><th>{T['amount']}</th><th>{T['check']}</th></tr>{receipt_rows}</table>
<p class="muted" style="margin-top:24px">Sijill · Powered by Gemma 4 · MIT License</p>
<script class="noprint">window.onload=()=>setTimeout(()=>window.print(),400)</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------
ASK_PROMPT = """You are a helpful personal finance assistant for a person living in Turkey.
Answer in {lang}, briefly and clearly. Use ONLY the data below; if the answer is not in the data, say so.
When you mention money, include the currency.

Summary (already converted to {cur}):
{summary}

Receipts:
{receipts}

Question: {question}"""


def ask(client, question: str, receipts: list[dict], summary: dict,
        lang: str = "ar", model: str = DEFAULT_MODEL) -> str:
    slim = [
        {k: r.get(k) for k in ("store_name", "date", "category", "total", "currency", "tax")}
        | {"items": [{"name": i.get("name_translated") or i.get("name_original"), "total": i.get("total")}
                     for i in (r.get("items") or [])][:30]}
        for r in receipts
    ]
    prompt = ASK_PROMPT.format(
        lang=LANG_NAMES.get(lang, "Arabic"),
        cur=summary.get("currency", "TRY"),
        summary=json.dumps(summary, ensure_ascii=False),
        receipts=json.dumps(slim, ensure_ascii=False, default=str)[:20000],
        question=question,
    )
    return _generate(client, model, prompt)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DATA_FILE = Path("data") / "receipts.json"


def load_receipts(path: Path | str = DATA_FILE) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_receipts(receipts: list[dict], path: Path | str = DATA_FILE) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipts, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)
