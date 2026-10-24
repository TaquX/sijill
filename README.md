# 🧾 سجلّ (Sijill)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Powered by Gemma 4](https://img.shields.io/badge/Model-Gemma%204-blue)](https://ai.google.dev/)

*Turn paper receipts into a smart expense table — in Arabic, Turkish and English. Powered by Gemma 4.*

حوّل الإيصالات الورقية إلى جدول مصاريف ذكي بصورة واحدة.

---

## 🔗 Live Application
👉 *Try it Live: [https://sijill.tech](https://sijill.tech) *(أدخل رابط التطبيق المباشر هنا)

---

## The problem
Small shops and Arabic-speaking residents in Turkey collect piles of Turkish paper receipts. Reading them is hard, tracking spending is manual, and OCR services cost money every month.

## The solution
1. Snap or upload receipts (Turkish, Arabic, or English).
2. *Gemma 4* reads each image and extracts store, date, items, prices, tax, and total, and translates item names.
3. Sijill checks that item totals match the receipt total (Self-Correction Audit).
4. You get an editable table, a spending-by-category chart, and Excel/CSV export.
5. Ask questions about your spending in plain Arabic.

## How Gemma 4 is used
- *Vision/OCR:* Gemma 4 (via the Gemini API) reads receipt images directly, with no separate OCR engine.
- *Multilingual:* Turkish receipt in, Arabic output out.
- *Reasoning:* categorization, plus Q&A over the extracted data.

## Tech stack
Python · Streamlit · Gemma 4 via Gemini API (google-genai) · pandas

## Run it locally
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your_key
streamlit run app.py
