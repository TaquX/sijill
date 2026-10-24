"""
سجلّ (Sijill) — حوّل صور الإيصالات إلى جدول مصاريف ذكي باستخدام Gemma 4
Sijill — Turn receipt photos into a smart expense table, powered by Gemma 4 (via Gemini API)
License: MIT
"""

import io
import json
import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

from ui import (LANG_CODES, footer, inject_css, metric_cards,
                receipt_cards, render_header, step_title)

# ---------------------------------------------------------------------------
# Page setup + RTL styling
# ---------------------------------------------------------------------------
st.set_page_config(page_title="سجلّ | Sijill", page_icon="🧾", layout="wide")


# ---------------------------------------------------------------------------
# Sidebar: settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ الإعدادات")
    api_key = st.text_input(
        "Gemini API Key", type="password", value=os.getenv("GEMINI_API_KEY", "")
    )
    # Check the exact Gemma 4 model ID in Google AI Studio and adjust if needed
    model_name = st.text_input("Model", value=os.getenv("GEMMA_MODEL", "gemma-4-31b-it"))
    out_lang = st.selectbox("لغة النتائج", ["العربية", "Türkçe", "English"])

    if st.button("📋 عرض نماذج Gemma المتاحة"):
        if not api_key:
            st.warning("أدخل مفتاح API أولاً")
        else:
            try:
                c = genai.Client(api_key=api_key)
                names = [m.name for m in c.models.list() if "gemma" in m.name.lower()]
                st.write(names or "لم يتم العثور على نماذج Gemma")
            except Exception as e:
                st.error(f"خطأ: {e}")

    if st.button("🗑️ مسح كل الإيصالات"):
        st.session_state.receipts = []
        st.rerun()

lang = LANG_CODES.get(out_lang, "ar")
inject_css(lang)
render_header(lang)

if "receipts" not in st.session_state:
    st.session_state.receipts = []

CATEGORIES = ["طعام وبقالة", "مطاعم ومقاهي", "مواصلات", "فواتير وخدمات",
              "صحة وأدوية", "ملابس", "إلكترونيات", "تعليم", "أخرى"]

# ---------------------------------------------------------------------------
# Gemma helpers
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
- If a value is unreadable, use null. Never invent items that are not on the receipt.
- "category" must be exactly one of the listed categories.
"""


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of the model's reply."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def read_receipt(client, image_bytes: bytes, mime: str) -> dict:
    prompt = EXTRACT_PROMPT.format(cats=", ".join(CATEGORIES), lang=out_lang)
    resp = client.models.generate_content(
        model=model_name,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime), prompt],
    )
    return extract_json(resp.text)


def check_totals(r: dict) -> str:
    """Verify that item totals add up to the receipt total."""
    try:
        s = sum(float(i.get("total") or 0) for i in r.get("items", []))
        t = float(r.get("total") or 0)
        if t == 0:
            return "⚠️ لا يوجد إجمالي"
        diff = abs(s - t)
        if diff <= 0.05 * t or diff < 1:
            return "✅ متطابق"
        return f"⚠️ فرق {diff:.2f}"
    except Exception:
        return "⚠️ تعذّر التحقق"


# ---------------------------------------------------------------------------
# 1) Upload receipts
# ---------------------------------------------------------------------------
step_title(1, "step1", lang)
col_a, col_b = st.columns(2)
with col_a:
    uploads = st.file_uploader(
        "ارفع صور الإيصالات", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True
    )
with col_b:
    cam = st.camera_input("أو صوّر الإيصال مباشرة")

files = list(uploads or [])
if cam:
    files.append(cam)

if files and st.button("🔍 اقرأ الإيصالات بـ Gemma 4", type="primary"):
    if not api_key:
        st.error("أدخل مفتاح Gemini API في الشريط الجانبي")
    else:
        client = genai.Client(api_key=api_key)
        progress = st.progress(0.0)
        for idx, f in enumerate(files):
            with st.spinner(f"جاري قراءة {f.name} ..."):
                try:
                    data = read_receipt(client, f.getvalue(), f.type or "image/jpeg")
                    data["_file"] = f.name
                    data["_check"] = check_totals(data)
                    st.session_state.receipts.append(data)
                except Exception as e:
                    st.error(f"تعذّرت قراءة {f.name}: {e}")
            progress.progress((idx + 1) / len(files))
        st.success("تمت القراءة ✅")

receipts = st.session_state.receipts
if not receipts:
    st.info("ارفع إيصالاً واحداً على الأقل للبدء.")
    st.stop()

# ---------------------------------------------------------------------------
# 2) Receipts table (editable)
# ---------------------------------------------------------------------------
step_title(2, "step2", lang)
receipt_cards(receipts, lang)
st.write("")
summary_df = pd.DataFrame(
    [
        {
            "المتجر": r.get("store_name"),
            "التاريخ": r.get("date"),
            "التصنيف": r.get("category"),
            "الإجمالي": r.get("total"),
            "العملة": r.get("currency"),
            "الضريبة": r.get("tax"),
            "التحقق": r.get("_check"),
            "ملاحظات": r.get("notes"),
        }
        for r in receipts
    ]
)
edited = st.data_editor(
    summary_df,
    use_container_width=True,
    column_config={"التصنيف": st.column_config.SelectboxColumn(options=CATEGORIES)},
    key="summary_editor",
)

items_rows = []
for r in receipts:
    for it in r.get("items", []):
        items_rows.append(
            {
                "المتجر": r.get("store_name"),
                "التاريخ": r.get("date"),
                "الصنف (الأصلي)": it.get("name_original"),
                "الصنف (مترجم)": it.get("name_translated"),
                "الكمية": it.get("qty"),
                "سعر الوحدة": it.get("unit_price"),
                "المجموع": it.get("total"),
            }
        )
items_df = pd.DataFrame(items_rows)
with st.expander(f"📦 كل الأصناف ({len(items_df)})"):
    st.dataframe(items_df, use_container_width=True)

# ---------------------------------------------------------------------------
# 3) Dashboard
# ---------------------------------------------------------------------------
step_title(3, "step3", lang)
edited["الإجمالي"] = pd.to_numeric(edited["الإجمالي"], errors="coerce").fillna(0)
main_cur = edited["العملة"].dropna().mode()
metric_cards(
    total=float(edited["الإجمالي"].sum()),
    count=len(edited),
    avg=float(edited["الإجمالي"].mean()),
    currency=str(main_cur.iloc[0]) if len(main_cur) else "",
    lang=lang,
)
st.write("")

by_cat = edited.groupby("التصنيف")["الإجمالي"].sum().sort_values(ascending=False)
st.bar_chart(by_cat)

# ---------------------------------------------------------------------------
# 4) Export
# ---------------------------------------------------------------------------
step_title(4, "step4", lang)
e1, e2 = st.columns(2)
with e1:
    st.download_button(
        "⬇️ تحميل CSV",
        edited.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"sijill_{datetime.now():%Y%m%d}.csv",
        mime="text/csv",
    )
with e2:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        edited.to_excel(xw, sheet_name="Receipts", index=False)
        items_df.to_excel(xw, sheet_name="Items", index=False)
    st.download_button(
        "⬇️ تحميل Excel",
        buf.getvalue(),
        file_name=f"sijill_{datetime.now():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ---------------------------------------------------------------------------
# 5) Ask about your expenses
# ---------------------------------------------------------------------------
step_title(5, "step5", lang)
question = st.text_input("مثال: أين صرفت أكثر شيء؟ هل يوجد إيصال فيه خطأ؟ اقترح عليّ طريقة للتوفير")
if question and api_key:
    client = genai.Client(api_key=api_key)
    context = json.dumps(
        {"receipts": edited.to_dict("records"), "items": items_df.to_dict("records")},
        ensure_ascii=False,
        default=str,
    )
    q_prompt = (
        f"You are a helpful personal finance assistant. Answer in {out_lang}, briefly and clearly.\n"
        f"Use ONLY this data:\n{context}\n\nQuestion: {question}"
    )
    with st.spinner("Gemma يفكّر..."):
        try:
            ans = client.models.generate_content(model=model_name, contents=q_prompt)
            st.markdown(ans.text)
        except Exception as e:
            st.error(f"خطأ: {e}")

footer(lang)
