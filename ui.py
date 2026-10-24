"""
ui.py — Sijill visual layer (theme, header, labels, cards).
Kept separate from app.py so it merges cleanly.
"""

import html

import streamlit as st

# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------
LANG_CODES = {"العربية": "ar", "Türkçe": "tr", "English": "en"}

TEXTS = {
    "ar": {
        "tagline": "صوّر إيصالاتك، ودع Gemma 4 يحوّلها إلى جدول مصاريف منظّم",
        "badge": "مدعوم بـ Gemma 4 · مفتوح المصدر",
        "step1": "أضف الإيصالات",
        "step2": "جدول الإيصالات",
        "step3": "ملخص المصاريف",
        "step4": "التصدير",
        "step5": "اسأل عن مصاريفك",
        "total": "إجمالي المصاريف",
        "count": "عدد الإيصالات",
        "avg": "متوسط الإيصال",
        "items": "صنف",
        "no_date": "بدون تاريخ",
        "footer": "صُنع في Hacktoberfest Hack Day Istanbul × Hadith Tech · ترخيص MIT",
    },
    "tr": {
        "tagline": "Fişlerinin fotoğrafını çek, Gemma 4 onları düzenli bir harcama tablosuna dönüştürsün",
        "badge": "Gemma 4 ile · Açık kaynak",
        "step1": "Fiş ekle",
        "step2": "Fiş tablosu",
        "step3": "Harcama özeti",
        "step4": "Dışa aktar",
        "step5": "Harcamalarını sor",
        "total": "Toplam harcama",
        "count": "Fiş sayısı",
        "avg": "Ortalama fiş",
        "items": "ürün",
        "no_date": "Tarih yok",
        "footer": "Hacktoberfest Hack Day Istanbul × Hadith Tech'te yapıldı · MIT lisansı",
    },
    "en": {
        "tagline": "Snap your receipts and let Gemma 4 turn them into a clean expense table",
        "badge": "Powered by Gemma 4 · Open source",
        "step1": "Add receipts",
        "step2": "Receipts table",
        "step3": "Spending summary",
        "step4": "Export",
        "step5": "Ask about your spending",
        "total": "Total spent",
        "count": "Receipts",
        "avg": "Average receipt",
        "items": "items",
        "no_date": "No date",
        "footer": "Built at Hacktoberfest Hack Day Istanbul × Hadith Tech · MIT License",
    },
}


_EXTRA = {'ar': {'settings': '⚙️ الإعدادات', 'language': '🌐 اللغة', 'list_models': '📋 عرض نماذج Gemma المتاحة', 'enter_key_first': 'أدخل مفتاح API أولاً', 'no_gemma': 'لم يتم العثور على نماذج Gemma', 'clear': '🗑️ مسح كل الإيصالات', 'upload_label': 'ارفع صور الإيصالات', 'use_camera': '📷 استخدم الكاميرا', 'camera_label': 'صوّر الإيصال', 'read_btn': '🔍 اقرأ الإيصالات بـ Gemma 4', 'need_key': 'أدخل مفتاح Gemini API في الشريط الجانبي', 'reading': 'جاري قراءة', 'read_ok': 'تمت القراءة ✅', 'read_fail': 'تعذّرت قراءة', 'start_info': 'ارفع إيصالاً واحداً على الأقل للبدء.', 'all_items': '📦 كل الأصناف', 'ask_placeholder': 'مثال: أين صرفت أكثر شيء؟ هل يوجد إيصال فيه خطأ؟', 'thinking': 'Gemma يفكّر...', 'error': 'خطأ', 'csv': '⬇️ تحميل CSV', 'excel': '⬇️ تحميل Excel'}, 'tr': {'settings': '⚙️ Ayarlar', 'language': '🌐 Dil', 'list_models': '📋 Mevcut Gemma modellerini göster', 'enter_key_first': 'Önce API anahtarını gir', 'no_gemma': 'Gemma modeli bulunamadı', 'clear': '🗑️ Tüm fişleri temizle', 'upload_label': 'Fiş fotoğraflarını yükle', 'use_camera': '📷 Kamerayı kullan', 'camera_label': 'Fişin fotoğrafını çek', 'read_btn': '🔍 Fişleri Gemma 4 ile oku', 'need_key': 'Kenar çubuğuna Gemini API anahtarını gir', 'reading': 'Okunuyor', 'read_ok': 'Okuma tamamlandı ✅', 'read_fail': 'Okunamadı', 'start_info': 'Başlamak için en az bir fiş yükle.', 'all_items': '📦 Tüm ürünler', 'ask_placeholder': 'Örnek: En çok nereye harcadım? Hatalı fiş var mı?', 'thinking': 'Gemma düşünüyor...', 'error': 'Hata', 'csv': '⬇️ CSV indir', 'excel': '⬇️ Excel indir'}, 'en': {'settings': '⚙️ Settings', 'language': '🌐 Language', 'list_models': '📋 Show available Gemma models', 'enter_key_first': 'Enter your API key first', 'no_gemma': 'No Gemma models found', 'clear': '🗑️ Clear all receipts', 'upload_label': 'Upload receipt photos', 'use_camera': '📷 Use camera', 'camera_label': 'Take a photo of the receipt', 'read_btn': '🔍 Read receipts with Gemma 4', 'need_key': 'Enter your Gemini API key in the sidebar', 'reading': 'Reading', 'read_ok': 'Done reading ✅', 'read_fail': 'Could not read', 'start_info': 'Upload at least one receipt to get started.', 'all_items': '📦 All items', 'ask_placeholder': 'e.g. Where did I spend the most? Is any receipt wrong?', 'thinking': 'Gemma is thinking...', 'error': 'Error', 'csv': '⬇️ Download CSV', 'excel': '⬇️ Download Excel'}}
for _code, _vals in _EXTRA.items():
    TEXTS[_code].update(_vals)


def t(key: str, lang: str = "ar") -> str:
    """Translated UI label, falling back to English, then to the key itself."""
    return TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"].get(key, key)


# Icons for the categories used in app.py
CATEGORY_ICONS = {
    "طعام وبقالة": "🛒",
    "مطاعم ومقاهي": "☕",
    "مواصلات": "🚕",
    "فواتير وخدمات": "💡",
    "صحة وأدوية": "💊",
    "ملابس": "👕",
    "إلكترونيات": "📱",
    "تعليم": "📚",
    "أخرى": "🧾",
}

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
LOGO_SVG = """
<svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <rect x="10" y="4" width="36" height="48" rx="4" fill="#FFFDF8" stroke="#0F766E" stroke-width="2.5"/>
  <path d="M10 46 l6 6 l6 -6 l6 6 l6 -6 l6 6 l6 -6" fill="none" stroke="#0F766E" stroke-width="2.5"/>
  <line x1="17" y1="16" x2="39" y2="16" stroke="#C08A2B" stroke-width="3" stroke-linecap="round"/>
  <line x1="17" y1="24" x2="33" y2="24" stroke="#0F766E" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="17" y1="31" x2="35" y2="31" stroke="#0F766E" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="37" cy="39" r="6" fill="#0F766E"/>
  <path d="M34.3 39 l2 2 l3.6 -3.8" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
</svg>
"""


def inject_css(lang: str = "ar") -> None:
    """Global styles. Arabic gets right-to-left layout."""
    rtl = lang == "ar"
    direction = "rtl" if rtl else "ltr"
    align = "right" if rtl else "left"
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;800&family=Inter:wght@400;600;800&display=swap');

        :root {{
            --sj-ink: #1F2933;
            --sj-muted: #6B7280;
            --sj-paper: #FFFDF8;
            --sj-teal: #0F766E;
            --sj-teal-soft: #E6F4F1;
            --sj-gold: #C08A2B;
            --sj-border: #E8E1D5;
            --sj-ok: #15803D;
            --sj-warn: #B45309;
        }}

        html, body, .stApp, .stMarkdown, p, label, h1, h2, h3, input, textarea, button {{
            font-family: {"'Cairo'" if rtl else "'Inter'"}, 'Segoe UI', Tahoma, sans-serif !important;
        }}
        .main .block-container, section[data-testid="stSidebar"] {{
            direction: {direction};
            text-align: {align};
        }}
        .main .block-container {{ max-width: 1150px; padding-top: 1.5rem; }}

        /* Tables stay left-to-right so numbers line up */
        [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ direction: ltr; }}

        /* Header */
        .sj-hero {{
            display: flex; align-items: center; gap: 1rem;
            background: linear-gradient(135deg, var(--sj-teal) 0%, #115E59 100%);
            color: #fff; border-radius: 18px; padding: 1.3rem 1.6rem; margin-bottom: 1.4rem;
        }}
        .sj-hero .sj-logo {{ background: #fff; border-radius: 14px; padding: 4px; display: flex; }}
        .sj-hero h1 {{ margin: 0; font-size: 2.1rem; font-weight: 800; color: #fff; line-height: 1.2; }}
        .sj-hero p {{ margin: .2rem 0 .5rem; opacity: .9; font-size: 1rem; }}
        .sj-badge {{
            display: inline-block; background: rgba(255,255,255,.16);
            border: 1px solid rgba(255,255,255,.35); border-radius: 999px;
            padding: .15rem .7rem; font-size: .8rem;
        }}

        /* Section titles */
        .sj-step {{
            display: flex; align-items: center; gap: .6rem;
            font-size: 1.25rem; font-weight: 800; color: var(--sj-ink);
            margin: 1.6rem 0 .7rem;
        }}
        .sj-step .num {{
            width: 2rem; height: 2rem; border-radius: 50%;
            background: var(--sj-teal); color: #fff;
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 1rem;
        }}

        /* Metric cards */
        .sj-metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: .8rem; }}
        .sj-metric {{
            background: var(--sj-paper); border: 1px solid var(--sj-border);
            border-radius: 14px; padding: 1rem 1.1rem;
        }}
        .sj-metric .label {{ color: var(--sj-muted); font-size: .85rem; }}
        .sj-metric .value {{ font-size: 1.7rem; font-weight: 800; color: var(--sj-ink); direction: ltr; }}
        .sj-metric.accent {{ background: var(--sj-teal-soft); border-color: #B7DFD7; }}
        .sj-metric.accent .value {{ color: var(--sj-teal); }}

        /* Receipt cards */
        .sj-cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: .8rem; }}
        .sj-card {{
            background: var(--sj-paper); border: 1px solid var(--sj-border);
            border-top: 4px solid var(--sj-gold); border-radius: 12px; padding: .9rem 1rem;
        }}
        .sj-card .store {{ font-weight: 800; font-size: 1.05rem; color: var(--sj-ink); }}
        .sj-card .meta {{ color: var(--sj-muted); font-size: .82rem; margin: .15rem 0 .5rem; }}
        .sj-card .amount {{ font-size: 1.4rem; font-weight: 800; color: var(--sj-teal); direction: ltr; display: inline-block; }}
        .sj-chip {{
            display: inline-block; font-size: .75rem; border-radius: 999px;
            padding: .1rem .55rem; margin-top: .5rem; border: 1px solid;
        }}
        .sj-chip.ok {{ color: var(--sj-ok); border-color: #BBE5C8; background: #F0FAF3; }}
        .sj-chip.warn {{ color: var(--sj-warn); border-color: #F5D9A8; background: #FFF8EB; }}

        /* Buttons */
        .stButton > button[kind="primary"], .stDownloadButton > button {{
            border-radius: 10px; font-weight: 700;
        }}

        .sj-footer {{
            text-align: center; color: var(--sj-muted); font-size: .8rem;
            margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--sj-border);
        }}

        @media (max-width: 640px) {{
            .sj-hero {{ flex-direction: column; text-align: center; }}
            .sj-hero h1 {{ font-size: 1.7rem; }}
            .sj-metrics {{ grid-template-columns: 1fr; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
def render_header(lang: str = "ar") -> None:
    st.markdown(
        f"""
        <div class="sj-hero">
          <div class="sj-logo">{LOGO_SVG}</div>
          <div>
            <h1>سجلّ <span style="font-weight:600;opacity:.75;font-size:1.3rem">Sijill</span></h1>
            <p>{t("tagline", lang)}</p>
            <span class="sj-badge">✨ {t("badge", lang)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def step_title(num: int, key: str, lang: str = "ar") -> None:
    """Numbered section heading, e.g. step_title(1, "step1", lang)."""
    st.markdown(
        f'<div class="sj-step"><span class="num">{num}</span>{t(key, lang)}</div>',
        unsafe_allow_html=True,
    )


def metric_cards(total: float, count: int, avg: float, currency: str = "", lang: str = "ar") -> None:
    cur = html.escape(currency or "")
    st.markdown(
        f"""
        <div class="sj-metrics">
          <div class="sj-metric accent"><div class="label">{t("total", lang)}</div>
            <div class="value">{total:,.2f} {cur}</div></div>
          <div class="sj-metric"><div class="label">{t("count", lang)}</div>
            <div class="value">{count}</div></div>
          <div class="sj-metric"><div class="label">{t("avg", lang)}</div>
            <div class="value">{avg:,.2f} {cur}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def receipt_cards(receipts: list, lang: str = "ar") -> None:
    """One card per receipt: store, date, category, total, verification chip."""
    cards = []
    for r in receipts:
        store = html.escape(str(r.get("store_name") or "—"))
        date = html.escape(str(r.get("date") or t("no_date", lang)))
        cat = r.get("category") or "أخرى"
        icon = CATEGORY_ICONS.get(cat, "🧾")
        try:
            total = f"{float(r.get('total') or 0):,.2f}"
        except (TypeError, ValueError):
            total = "—"
        cur = html.escape(str(r.get("currency") or ""))
        n_items = len(r.get("items") or [])
        check = str(r.get("_check") or "")
        chip_class = "ok" if check.startswith("✅") else "warn"
        cards.append(
            f"""
            <div class="sj-card">
              <div class="store">{icon} {store}</div>
              <div class="meta">{date} · {html.escape(cat)} · {n_items} {t("items", lang)}</div>
              <div class="amount">{total} {cur}</div><br>
              <span class="sj-chip {chip_class}">{html.escape(check)}</span>
            </div>
            """
        )
    st.markdown(f'<div class="sj-cards">{"".join(cards)}</div>', unsafe_allow_html=True)


def footer(lang: str = "ar") -> None:
    st.markdown(f'<div class="sj-footer">{t("footer", lang)}</div>', unsafe_allow_html=True)
