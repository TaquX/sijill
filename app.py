"""
سجلّ (Sijill) — حوّل صور الإيصالات إلى جدول مصاريف ذكي باستخدام Gemma 4
Sijill — Turn receipt photos into a smart expense table, powered by Gemma 4 (via Gemini API)

This file is only the Streamlit screen. All logic lives in backend.py.
License: MIT
"""

import io
import os
from datetime import datetime

import pandas as pd
import streamlit as st

import backend as be
from ui import (LANG_CODES, footer, inject_css, metric_cards,
                receipt_cards, render_header, step_title, t)

st.set_page_config(page_title="سجلّ | Sijill", page_icon="🧾", layout="wide")

CURRENCIES = ["TRY", "USD", "EUR", "SAR", "AED", "GBP"]

# ---------------------------------------------------------------------------
# State: receipts survive a page refresh (saved in data/receipts.json)
# ---------------------------------------------------------------------------
if "receipts" not in st.session_state:
    st.session_state.receipts = be.load_receipts()
if "ver" not in st.session_state:
    st.session_state.ver = 0  # bumps when the list changes, resets the table editor


def save_and_bump():
    be.save_receipts(st.session_state.receipts)
    st.session_state.ver += 1


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
lang = LANG_CODES.get(st.session_state.get("out_lang", "العربية"), "ar")

with st.sidebar:
    st.header(t("settings", lang))
    api_key = st.text_input("Gemini API Key", type="password", value=os.getenv("GEMINI_API_KEY", ""))
    # Check the exact Gemma 4 model ID with the button below and adjust if needed
    model_name = st.text_input("Model", value=os.getenv("GEMMA_MODEL", be.DEFAULT_MODEL))
    out_lang = st.selectbox(t("language", lang), ["العربية", "Türkçe", "English"], key="out_lang")
    display_cur = st.selectbox(t("display_currency", lang), CURRENCIES, key="display_cur")

    if st.button(t("list_models", lang)):
        if not api_key:
            st.warning(t("enter_key_first", lang))
        else:
            try:
                st.write(be.list_gemma_models(be.get_client(api_key)) or t("no_gemma", lang))
            except Exception as e:
                st.error(f"{t('error', lang)}: {e}")

    if st.button(t("clear", lang)):
        st.session_state.receipts = []
        save_and_bump()
        st.rerun()

lang = LANG_CODES.get(out_lang, "ar")
inject_css(lang)
render_header(lang)

receipts = be.relabel(st.session_state.receipts, lang)

# ---------------------------------------------------------------------------
# 1) Add receipts
# ---------------------------------------------------------------------------
step_title(1, "step1", lang)
col_a, col_b = st.columns(2)
with col_a:
    uploads = st.file_uploader(
        t("upload_label", lang), type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True, key=f"uploader_{st.session_state.ver}",
    )
with col_b:
    cam = None
    if st.toggle(t("use_camera", lang)):
        cam = st.camera_input(t("camera_label", lang))

files = list(uploads or [])
if cam:
    files.append(cam)

if files and st.button(t("read_btn", lang), type="primary"):
    if not api_key:
        st.error(t("need_key", lang))
    else:
        client = be.get_client(api_key)
        progress = st.progress(0.0)
        added = 0
        for idx, f in enumerate(files):
            with st.spinner(f"{t('reading', lang)} {f.name} ..."):
                try:
                    r = be.read_receipt(client, f.getvalue(), f.type, lang=lang, model=model_name)
                    if be.is_duplicate(r, receipts):
                        st.warning(f"{t('duplicate_skip', lang)}: {f.name}")
                    else:
                        receipts.append(be.finalize(r, f.name, lang))
                        added += 1
                except be.NotAReceiptError:
                    st.warning(f"{t('not_receipt', lang)}: {f.name}")
                except Exception as e:
                    st.error(f"{t('read_fail', lang)} {f.name}: {e}")
            progress.progress((idx + 1) / len(files))
        if added:
            save_and_bump()
            st.success(f"{t('read_ok', lang)} ({added})")
            st.rerun()

if not receipts:
    st.info(t("start_info", lang))
    footer(lang)
    st.stop()

# ---------------------------------------------------------------------------
# 2) Receipts: cards + editable table (edits and deletions are saved)
# ---------------------------------------------------------------------------
step_title(2, "step2", lang)
receipt_cards(receipts, lang)
st.write("")

EDIT_MAP = {"المتجر": "store_name", "التاريخ": "date", "التصنيف": "category",
            "الإجمالي": "total", "العملة": "currency", "الضريبة": "tax", "ملاحظات": "notes"}
DEL = "🗑️"

summary_df = pd.DataFrame(
    [{DEL: False, **{col: r.get(key) for col, key in EDIT_MAP.items()}, "التحقق": r.get("_check")}
     for r in receipts],
    index=[r["id"] for r in receipts],
)
edited = st.data_editor(
    summary_df,
    use_container_width=True,
    hide_index=True,
    disabled=["التحقق"],
    column_config={
        DEL: st.column_config.CheckboxColumn(t("delete_col", lang), width="small"),
        "التصنيف": st.column_config.SelectboxColumn(options=be.CATEGORIES),
        "العملة": st.column_config.SelectboxColumn(options=sorted(set(CURRENCIES) | {r.get("currency") or "TRY" for r in receipts})),
        "الإجمالي": st.column_config.NumberColumn(format="%.2f"),
        "الضريبة": st.column_config.NumberColumn(format="%.2f"),
    },
    key=f"editor_{st.session_state.ver}",
)

# Apply table edits back to the stored receipts
changed = False
by_id = {r["id"]: r for r in receipts}
for rid, row in edited.iterrows():
    r = by_id.get(rid)
    if r is None:
        continue
    for col, key in EDIT_MAP.items():
        new = row[col]
        new = None if pd.isna(new) else (float(new) if key in ("total", "tax") else str(new))
        if new != r.get(key):
            r[key] = new
            changed = True
to_delete = set(edited.index[edited[DEL]]) if DEL in edited else set()
if to_delete:
    st.session_state.receipts = [r for r in receipts if r["id"] not in to_delete]
    save_and_bump()
    st.rerun()
if changed:
    be.relabel(receipts, lang)
    be.save_receipts(receipts)

items_df = pd.DataFrame(
    [{"المتجر": r.get("store_name"), "التاريخ": r.get("date"),
      "الصنف (الأصلي)": it.get("name_original"), "الصنف (مترجم)": it.get("name_translated"),
      "الكمية": it.get("qty"), "سعر الوحدة": it.get("unit_price"), "المجموع": it.get("total")}
     for r in receipts for it in (r.get("items") or [])]
)
with st.expander(f"{t('all_items', lang)} ({len(items_df)})"):
    st.dataframe(items_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# 3) Summary (all amounts converted to the chosen currency)
# ---------------------------------------------------------------------------
step_title(3, "step3", lang)
rates, live = be.get_rates(display_cur)
summary = be.summarize(receipts, display_cur, rates)
metric_cards(summary["total"], summary["count"], summary["average"], display_cur, lang)
if not live and any((r.get("currency") or "TRY") != display_cur for r in receipts):
    st.caption(t("rates_fallback", lang))
st.write("")

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**{t('by_category', lang)}**")
    st.bar_chart(pd.Series(summary["by_category"], name=display_cur))
with c2:
    st.markdown(f"**{t('by_month', lang)}**")
    st.bar_chart(pd.Series(summary["by_month"], name=display_cur))

# ---------------------------------------------------------------------------
# 4) Export
# ---------------------------------------------------------------------------
step_title(4, "step4", lang)
export_df = edited.drop(columns=[DEL], errors="ignore")
stamp = f"{datetime.now():%Y%m%d}"
e1, e2, e3 = st.columns(3)
with e1:
    st.download_button(t("csv", lang), export_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"sijill_{stamp}.csv", mime="text/csv")
with e2:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        export_df.to_excel(xw, sheet_name="Receipts", index=False)
        items_df.to_excel(xw, sheet_name="Items", index=False)
    st.download_button(t("excel", lang), buf.getvalue(), file_name=f"sijill_{stamp}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
with e3:
    st.download_button(t("report", lang), be.report_html(receipts, summary, lang).encode("utf-8"),
                       file_name=f"sijill_report_{stamp}.html", mime="text/html")

# ---------------------------------------------------------------------------
# 5) Ask about your spending
# ---------------------------------------------------------------------------
step_title(5, "step5", lang)
question = st.text_input(t("ask_placeholder", lang))
if question:
    if not api_key:
        st.error(t("need_key", lang))
    else:
        with st.spinner(t("thinking", lang)):
            try:
                st.markdown(be.ask(be.get_client(api_key), question, receipts, summary, lang, model_name))
            except Exception as e:
                st.error(f"{t('error', lang)}: {e}")

footer(lang)
