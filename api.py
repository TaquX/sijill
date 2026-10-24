"""
api.py — Sijill REST API (optional).

Exposes the same backend as the Streamlit app, so a mobile app, a shop's POS,
or a Telegram bot could send receipts to Sijill.

Run:
    export GEMINI_API_KEY=your_key
    uvicorn api:app --reload --port 8000
Docs (interactive): http://localhost:8000/docs

License: MIT
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import backend as be

Lang = Literal["ar", "tr", "en"]

app = FastAPI(
    title="Sijill API",
    description="Turn receipt photos into structured expense data with Gemma 4.",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MODEL = os.getenv("GEMMA_MODEL", be.DEFAULT_MODEL)
DATA_FILE = os.getenv("SIJILL_DATA", str(be.DATA_FILE))
MAX_UPLOAD = 15 * 1024 * 1024  # 15 MB


def _client():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(500, "GEMINI_API_KEY is not set on the server")
    return be.get_client(key)


class AskBody(BaseModel):
    question: str
    lang: Lang = "ar"
    currency: str = "TRY"


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "receipts": len(be.load_receipts(DATA_FILE))}


@app.post("/receipts")
async def add_receipt(
    file: UploadFile = File(..., description="Receipt photo (JPG/PNG/WEBP)"),
    lang: Lang = Query("ar"),
    allow_duplicate: bool = Query(False),
):
    """Read a receipt photo with Gemma 4 and store it."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 15 MB)")
    try:
        receipt = be.read_receipt(_client(), data, file.content_type, lang=lang, model=MODEL)
    except be.NotAReceiptError as e:
        raise HTTPException(422, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Gemma could not read the receipt: {e}")

    receipts = be.load_receipts(DATA_FILE)
    duplicate = be.is_duplicate(receipt, receipts)
    if duplicate and not allow_duplicate:
        return {"duplicate": True, "receipt": be.finalize(receipt, file.filename or "", lang)}
    final = be.finalize(receipt, file.filename or "", lang)
    receipts.append(final)
    be.save_receipts(receipts, DATA_FILE)
    return {"duplicate": duplicate, "receipt": final}


@app.get("/receipts")
def list_receipts(lang: Lang = Query("ar")):
    return be.relabel(be.load_receipts(DATA_FILE), lang)


@app.delete("/receipts/{receipt_id}")
def delete_receipt(receipt_id: str):
    receipts = be.load_receipts(DATA_FILE)
    kept = [r for r in receipts if r.get("id") != receipt_id]
    if len(kept) == len(receipts):
        raise HTTPException(404, "Receipt not found")
    be.save_receipts(kept, DATA_FILE)
    return {"deleted": receipt_id}


@app.delete("/receipts")
def clear_receipts():
    be.save_receipts([], DATA_FILE)
    return {"deleted": "all"}


@app.get("/summary")
def summary(currency: str = Query("TRY", min_length=3, max_length=3)):
    rates, live = be.get_rates(currency)
    s = be.summarize(be.load_receipts(DATA_FILE), currency, rates)
    s["live_rates"] = live
    return s


@app.get("/report", response_class=HTMLResponse)
def report(currency: str = Query("TRY", min_length=3, max_length=3), lang: Lang = Query("ar")):
    receipts = be.relabel(be.load_receipts(DATA_FILE), lang)
    rates, _ = be.get_rates(currency)
    return be.report_html(receipts, be.summarize(receipts, currency, rates), lang)


@app.post("/ask")
def ask(body: AskBody):
    receipts = be.load_receipts(DATA_FILE)
    if not receipts:
        raise HTTPException(400, "No receipts yet")
    rates, _ = be.get_rates(body.currency)
    s = be.summarize(receipts, body.currency, rates)
    try:
        answer = be.ask(_client(), body.question, receipts, s, lang=body.lang, model=MODEL)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Gemma error: {e}")
    return {"answer": answer}
