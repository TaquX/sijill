"""API tests with a fake Gemma — no key or internet needed."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import backend as be  # noqa: E402
from tests.test_backend import BIM, FakeClient, tiny_png  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DATA_FILE", str(tmp_path / "receipts.json"))
    monkeypatch.setattr(be, "get_rates", lambda base="TRY", timeout=5.0: ({"TRY": 1.0, "USD": 0.025}, False))
    return TestClient(api.app)


def use_fake(monkeypatch, *replies):
    fake = FakeClient(*replies)
    monkeypatch.setattr(api, "_client", lambda: fake)
    return fake


def upload(c, **params):
    return c.post("/receipts", params=params, files={"file": ("bim.png", tiny_png(), "image/png")})


def test_full_flow(client, monkeypatch):
    use_fake(monkeypatch, json.dumps(BIM), json.dumps(BIM), "BİM")
    r = upload(client, lang="en")
    assert r.status_code == 200 and r.json()["duplicate"] is False
    rid = r.json()["receipt"]["id"]
    assert r.json()["receipt"]["_check"] == "✅ Totals match"

    # second upload of the same receipt is flagged and not stored
    r2 = upload(client)
    assert r2.json()["duplicate"] is True
    assert len(client.get("/receipts").json()) == 1

    s = client.get("/summary", params={"currency": "TRY"}).json()
    assert s["total"] == 72.5 and s["count"] == 1

    assert "<!doctype html>" in client.get("/report", params={"lang": "tr"}).text
    assert client.post("/ask", json={"question": "where?", "lang": "en"}).json()["answer"] == "BİM"

    assert client.delete(f"/receipts/{rid}").status_code == 200
    assert client.get("/receipts").json() == []
    assert client.delete("/receipts/nope").status_code == 404


def test_not_a_receipt(client, monkeypatch):
    use_fake(monkeypatch, '{"error": "not_a_receipt"}')
    assert upload(client).status_code == 422


def test_empty_file(client):
    r = client.post("/receipts", files={"file": ("x.png", b"", "image/png")})
    assert r.status_code == 400


def test_missing_key(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert upload(client).status_code == 500


def test_ask_without_receipts(client):
    assert client.post("/ask", json={"question": "hi"}).status_code == 400
