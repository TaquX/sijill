"""Backend tests — run with:  python -m pytest -q
No API key or internet needed: Gemma is replaced by a fake client."""

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backend as be  # noqa: E402


# --- fake Gemma -------------------------------------------------------------
class _Resp:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate_content(self, model, contents):
        self.calls += 1
        return _Resp(self.replies.pop(0))


class FakeClient:
    def __init__(self, *replies):
        self.models = FakeModels(replies)


def tiny_png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 60), "white").save(buf, format="PNG")
    return buf.getvalue()


BIM = {
    "store_name": "BİM", "date": "20.10.2026", "currency": "TL", "category": "طعام وبقالة",
    "items": [
        {"name_original": "SÜT", "name_translated": "حليب", "qty": 2, "unit_price": "30,00", "total": "60,00"},
        {"name_original": "EKMEK", "name_translated": "خبز", "qty": 1, "unit_price": "12,50", "total": None},
    ],
    "tax": "7,25", "total": "72,50", "notes": "",
}


# --- parsing ----------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("12,50", 12.5), ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("₺ 45", 45.0),
    ("TL 7,25", 7.25), (99, 99.0), (None, None), ("", None), ("abc", None), ("1.234.567", 1234567.0),
])
def test_to_number(raw, expected):
    assert be.to_number(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-10-20", "2026-10-20"), ("20.10.2026", "2026-10-20"), ("20/10/26", "2026-10-20"),
    ("Tarih: 05.03.2026 14:22", "2026-03-05"), ("garbage", None), (None, None),
])
def test_to_iso_date(raw, expected):
    assert be.to_iso_date(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("TL", "TRY"), ("₺", "TRY"), ("try", "TRY"), ("$", "USD"), ("EUR", "EUR"), (None, "TRY"), ("12 ₺", "TRY"),
])
def test_to_currency(raw, expected):
    assert be.to_currency(raw) == expected


def test_extract_json_variants():
    assert be.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert be.extract_json('Sure! Here it is: {"a": {"b": "x}"}, } thanks') == {"a": {"b": "x}"}}
    assert be.extract_json('{"a": [1, 2,],}') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        be.extract_json("no json here")


def test_normalize_fills_and_cleans():
    r = be.normalize_receipt(BIM)
    assert r["date"] == "2026-10-20" and r["currency"] == "TRY" and r["total"] == 72.5
    assert r["items"][1]["total"] == 12.5  # computed from qty * unit_price
    assert r["tax"] == 7.25
    assert be.normalize_receipt({"category": "Food", "total": 5})["category"] == be.OTHER


# --- verification & duplicates ----------------------------------------------
def test_verify_statuses():
    r = be.normalize_receipt(BIM)
    assert be.verify(r)["status"] == "ok"
    bad = dict(r, total=150.0)
    v = be.verify(bad)
    assert v["status"] == "mismatch" and v["diff"] == 77.5
    assert be.verify({"items": [], "total": None})["status"] == "no_total"
    assert be.verify({"items": [], "total": 10})["status"] == "no_items"
    assert be.check_label(v, "en") == "⚠️ Off by 77.50"


def test_duplicates():
    r = be.finalize(be.normalize_receipt(BIM), "a.jpg")
    again = be.normalize_receipt(BIM)
    assert be.is_duplicate(again, [r])
    assert not be.is_duplicate(dict(again, total=1.0), [r])


# --- reading with a fake Gemma ------------------------------------------------
def test_read_receipt_happy_path():
    client = FakeClient(json.dumps(BIM, ensure_ascii=False))
    r = be.read_receipt(client, tiny_png(), "image/png", lang="ar")
    assert r["store_name"] == "BİM" and r["total"] == 72.5
    assert client.models.calls == 1


def test_read_receipt_repairs_bad_json():
    client = FakeClient("this is not json", json.dumps(BIM))
    r = be.read_receipt(client, tiny_png(), "image/png")
    assert r["total"] == 72.5 and client.models.calls == 2


def test_read_receipt_gives_up():
    client = FakeClient("nope", "still nope", "nope again")
    with pytest.raises(ValueError):
        be.read_receipt(client, tiny_png(), "image/png", retries=2)


def test_not_a_receipt():
    client = FakeClient('{"error": "not_a_receipt"}')
    with pytest.raises(be.NotAReceiptError):
        be.read_receipt(client, tiny_png(), "image/png")


def test_prepare_image_shrinks():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (4000, 3000), "white").save(buf, format="PNG")
    out, mime = be.prepare_image(buf.getvalue(), "image/png")
    assert mime == "image/jpeg"
    assert max(Image.open(io.BytesIO(out)).size) <= be.MAX_SIDE
    assert be.prepare_image(b"not an image", "image/png") == (b"not an image", "image/png")


# --- currency, summary, report, storage ---------------------------------------
RATES_TO_USD = {"USD": 1.0, "TRY": 40.0, "EUR": 0.9}


def test_convert():
    assert be.convert(400, "TRY", "USD", RATES_TO_USD) == 10.0
    assert be.convert(5, "USD", "USD", RATES_TO_USD) == 5.0
    assert be.convert(5, "XYZ", "USD", RATES_TO_USD) is None
    assert be.convert(None, "TRY", "USD", RATES_TO_USD) is None


def test_fallback_rates_offline(monkeypatch):
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(be.urllib.request, "urlopen", boom)
    be._RATES_CACHE.clear()
    rates, live = be.get_rates("USD")
    assert live is False and rates["USD"] == 1.0 and rates["TRY"] > 1


def test_summarize_and_report():
    a = be.finalize(be.normalize_receipt(BIM), "a.jpg")
    b = be.finalize(be.normalize_receipt({"store_name": "Cafe", "date": "2026-09-02", "currency": "USD",
                                          "category": "مطاعم ومقاهي", "items": [], "total": 3}), "b.jpg")
    s = be.summarize([a, b], "USD", RATES_TO_USD)
    assert s["total"] == round(72.5 / 40 + 3, 2)
    assert list(s["by_month"]) == ["2026-09", "2026-10"]
    assert s["count"] == 2 and s["unconverted"] == 0
    page = be.report_html([a, b], s, lang="en")
    assert "<!doctype html>" in page and "Expense Report" in page and "BİM" in page
    assert be.report_html([a], s, lang="ar").count('dir="rtl"') == 1


def test_report_escapes_html():
    r = be.finalize(be.normalize_receipt({"store_name": "<script>x</script>", "total": 5, "items": []}))
    page = be.report_html([r], be.summarize([r], "TRY", {"TRY": 1.0}), "en")
    assert "<script>x</script>" not in page


def test_storage_roundtrip(tmp_path):
    path = tmp_path / "d" / "r.json"
    assert be.load_receipts(path) == []
    r = be.finalize(be.normalize_receipt(BIM))
    be.save_receipts([r], path)
    assert be.load_receipts(path)[0]["id"] == r["id"]
    path.write_text("{broken", encoding="utf-8")
    assert be.load_receipts(path) == []


def test_ask_uses_data():
    client = FakeClient("أكثر مصروف كان في BİM")
    r = be.finalize(be.normalize_receipt(BIM))
    ans = be.ask(client, "أين صرفت أكثر؟", [r], be.summarize([r], "TRY", {"TRY": 1.0}), lang="ar")
    assert "BİM" in ans
