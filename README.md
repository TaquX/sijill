# 🧾 سجلّ (Sijill)

**Turn paper receipts into a smart expense table — in Arabic, Turkish and English. Powered by Gemma 4.**

حوّل الإيصالات الورقية إلى جدول مصاريف ذكي بصورة واحدة.

## The problem
Small shops and Arabic-speaking residents in Turkey collect piles of Turkish paper receipts. Reading them is hard, tracking spending is manual, and OCR services cost money every month.

## The solution
1. Snap or upload receipts (Turkish, Arabic, or English).
2. **Gemma 4** reads each image and extracts store, date, items, prices, tax, and total, and translates item names.
3. Sijill checks that item totals match the receipt total.
4. Duplicate receipts are detected, and photos that aren't receipts are rejected.
5. You get an editable table, charts by category and month, and Excel/CSV export.
6. Totals are converted into one currency (TRY, USD, EUR, SAR, AED, GBP) with live exchange rates.
7. A printable monthly report for small shops (open it and print or save as PDF).
8. Ask questions about your spending in plain Arabic, Turkish, or English.

## How Gemma 4 is used
- **Vision/OCR:** Gemma 4 (via the Gemini API) reads receipt images directly, with no separate OCR engine.
- **Multilingual:** Turkish receipt in, Arabic output out.
- **Reasoning:** categorization, plus Q&A over the extracted data.

## Architecture

```
app.py      Streamlit screen (UI only)
ui.py       Theme, labels in 3 languages, cards
backend.py  The engine: Gemma 4 calls, JSON repair + retry, Turkish number/date
            parsing, total verification, duplicates, currency, report, Q&A, storage
api.py      REST API (FastAPI) on top of the same backend
tests/      43 tests with a fake Gemma, no API key needed
```

How a receipt is processed: photo → auto-rotate and resize → Gemma 4 reads it as JSON →
if the JSON is broken, Gemma is asked to repair it (up to 2 retries) → numbers like `1.234,56`
and dates like `20.10.2026` are normalized → item totals are checked against the receipt total →
duplicate check → saved to `data/receipts.json`.

## REST API

```bash
export GEMINI_API_KEY=your_key
uvicorn api:app --reload --port 8000
```
Interactive docs at `http://localhost:8000/docs`.

| Method | Path | What it does |
|---|---|---|
| POST | `/receipts?lang=ar` | Upload a receipt photo, Gemma 4 reads and stores it |
| GET | `/receipts` | List stored receipts |
| DELETE | `/receipts/{id}` | Delete one receipt |
| GET | `/summary?currency=USD` | Totals by category, month, store |
| GET | `/report?lang=tr&currency=TRY` | Printable HTML report |
| POST | `/ask` | Ask a question about your spending |

## Tests
```bash
python -m pytest -q
```

## Tech stack
Python · Streamlit · FastAPI · Gemma 4 via Gemini API (`google-genai`) · pandas · Pillow

## Run it
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=your_key
streamlit run app.py
```

## Built at
Hacktoberfest Hack Day Istanbul x Hadith Tech — October 24, 2026

## License
MIT
