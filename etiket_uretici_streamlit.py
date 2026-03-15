import io
import re
import csv
import html
from typing import List, Dict

import pandas as pd
import pdfplumber
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle, PageBreak

st.set_page_config(page_title="Etiket Hazırlama", page_icon="🏷️", layout="centered")

# ---------------------------------------------------
# SABİTLER
# ---------------------------------------------------
LABEL_W = 6 * cm
LABEL_H = 3 * cm
COLS = 3
COL_GAP = 0.5 * cm
ROW_GAP = 0.5 * cm

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

if "DejaVuSans" not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_REGULAR))
if "DejaVuSans-Bold" not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", FONT_BOLD))

BASE_STYLE = ParagraphStyle(
    "base",
    fontName="DejaVuSans",
    fontSize=8,
    leading=8.3,
    spaceAfter=0,
    spaceBefore=0,
)

LASER_STYLE = ParagraphStyle(
    "laser",
    parent=BASE_STYLE,
    fontName="DejaVuSans",
    fontSize=5,
    leading=5.6,
    wordWrap="CJK",
    spaceAfter=0,
    spaceBefore=0,
)

ADDRESS_HINTS = [
    "street", "st ", " st", "ave", "avenue", "road", "rd", "house", "apt", "apartment",
    "flat", "dr", "drive", "cir", "circle", "prospect", "domain", "kentfield", "winston",
    "valmont", "central", "augusta", "village", "park", "cordova", "barking", "ashburn",
    "buffalo", "new haven", "austin", "cookeville", "belfast",
]

STOP_LINE_PREFIXES = (
    "ring size", "width", "personalization", "gemstone type", "shipping service", "13.", "https://", "shipentegra"
)

# ---------------------------------------------------
# CSS / TEMA
# ---------------------------------------------------
st.markdown("""
<style>
:root {
    --etsy-orange: #F1641E;
    --etsy-orange-dark: #D65214;
    --etsy-orange-soft: #FFF3EC;
    --border-soft: #F3D6C7;
    --text-dark: #2B2B2B;
}

html, body, [class*="css"] {
    font-family: "Inter", "Segoe UI", sans-serif;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 900px;
}

.hero-box {
    background: linear-gradient(135deg, #FFF6F1 0%, #FFFFFF 100%);
    border: 1px solid var(--border-soft);
    border-radius: 18px;
    padding: 24px 22px;
    margin-bottom: 18px;
}

.hero-title {
    font-size: 30px;
    font-weight: 800;
    color: var(--text-dark);
    margin-bottom: 6px;
}

.hero-sub {
    font-size: 15px;
    color: #555;
    margin-bottom: 0;
}

.step-strip {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin: 14px 0 4px 0;
}

.step-pill {
    background: white;
    border: 1px solid var(--border-soft);
    color: #444;
    border-radius: 999px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 600;
}

.info-card {
    background: #fff;
    border: 1px solid #eee;
    border-left: 5px solid var(--etsy-orange);
    border-radius: 14px;
    padding: 14px 16px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}

.info-label {
    font-size: 12px;
    color: #777;
    margin-bottom: 4px;
}

.info-value {
    font-size: 22px;
    font-weight: 800;
    color: var(--text-dark);
    line-height: 1.2;
}

.section-title {
    font-size: 18px;
    font-weight: 800;
    color: var(--text-dark);
    margin-top: 10px;
    margin-bottom: 8px;
}

.stFileUploader {
    background: #fff;
    border: 1px dashed var(--etsy-orange);
    border-radius: 16px;
    padding: 10px;
}

.stDownloadButton > button {
    width: 100%;
    border-radius: 12px !important;
    border: 1px solid var(--etsy-orange) !important;
    background: var(--etsy-orange) !important;
    color: white !important;
    font-weight: 700 !important;
    min-height: 48px;
}

.stDownloadButton > button:hover {
    background: var(--etsy-orange-dark) !important;
    border-color: var(--etsy-orange-dark) !important;
    color: white !important;
}

div[data-testid="stExpander"] {
    border: 1px solid #eee;
    border-radius: 14px;
    overflow: hidden;
}

div[data-testid="stTabs"] button {
    font-weight: 700;
}

.status-ok {
    background: #F4FFF6;
    border: 1px solid #CDEFD5;
    color: #215B2B;
    border-radius: 12px;
    padding: 12px 14px;
    margin: 10px 0 16px 0;
    font-weight: 600;
}

.footer-note {
    text-align: center;
    color: #777;
    font-size: 13px;
    margin-top: 24px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------
# YARDIMCI FONKSİYONLAR
# ---------------------------------------------------
def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def first_nonempty(*values):
    for v in values:
        val = clean_text(str(v))
        if val:
            return val
    return ""


def us_size_to_decimal(text: str) -> str:
    raw = clean_text((text or "").upper().replace("US", "").strip())
    if not raw:
        return ""
    try:
        if " " in raw and "/" in raw:
            base, frac = raw.split(" ", 1)
            num, den = frac.split("/", 1)
            value = float(base) + (float(num) / float(den))
        elif "/" in raw:
            num, den = raw.split("/", 1)
            value = float(num) / float(den)
        else:
            value = float(raw)
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    except Exception:
        return clean_text(text)


def truncate_text(text: str, max_len: int) -> str:
    text = clean_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def strip_footer_noise(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{1,2}/\d{1,2}\b", "", text)
    text = re.sub(r"\bShipentegra\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"printmultipleorders", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}\b", "", text)
    return text


def normalize_lines(text: str) -> List[str]:
    text = strip_footer_noise(text)
    return [clean_text(x) for x in text.splitlines() if clean_text(x)]


def is_address_like(line: str) -> bool:
    low = line.lower()
    if any(h in low for h in ADDRESS_HINTS):
        return True
    if re.search(r"\b(?:GB|US|IE)\b", line):
        return True
    if re.search(r"\b[A-Z]{2}\d{4,}", line):
        return True
    if re.search(r"\d{1,6}", line) and len(line.split()) >= 2:
        return True
    return False


def extract_order_no(page_text: str) -> str:
    m = re.search(r"Sipariş Numarası\s*(\d+)", page_text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def find_customer_name(page_text: str) -> str:
    lines = normalize_lines(page_text)
    date_re = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

    def is_stop_line(candidate: str) -> bool:
        low = candidate.lower()
        if candidate in {"Sipariş Numarası", "Sipariş Ürünleri"}:
            return True
        if date_re.search(candidate):
            return True
        if re.search(r"\b(?:GEÇİLDİ|STOK|Ş)\b", candidate):
            return True
        if re.search(r"\b(?:GB|US|IE)\b", candidate):
            return True
        if is_address_like(candidate):
            return True
        if any(x in low for x in ["wedding band", "ring", "gold", "silver", "vermeil", "promise", "service", "solitaire"]):
            return True
        return False

    for i, line in enumerate(lines):
        if line == "Alıcı Adres Sipariş Tarihi Kendi Notum":
            name_parts = []
            for candidate in lines[i + 1:i + 8]:
                if is_stop_line(candidate):
                    break
                if candidate and not any(ch.isdigit() for ch in candidate):
                    name_parts.append(candidate)
                else:
                    break
            joined = clean_text(" ".join(name_parts))
            if joined and len(joined.split()) >= 2:
                return joined

    top_section = []
    for line in lines:
        if line == "Sipariş Numarası":
            break
        top_section.append(line)

    current_parts = []
    for line in top_section:
        if line in {"Sipariş Bilgileri", "Alıcı Adres Sipariş Tarihi Kendi Notum", "Sipariş Ürünleri"}:
            continue
        if is_stop_line(line):
            if len(current_parts) >= 2:
                return clean_text(" ".join(current_parts))
            current_parts = []
            continue
        if line and not any(ch.isdigit() for ch in line):
            current_parts.append(line)
        else:
            if len(current_parts) >= 2:
                return clean_text(" ".join(current_parts))
            current_parts = []

    if len(current_parts) >= 2:
        return clean_text(" ".join(current_parts))

    return ""


def split_products(page_text: str) -> List[str]:
    page_text = strip_footer_noise(page_text)
    parts = re.split(r"(?=Adet:\s*\d+)", page_text)
    return [p.strip() for p in parts if re.search(r"Adet:\s*\d+", p)]


def extract_product_title(block: str) -> str:
    lines = normalize_lines(block)
    started = False
    title_lines = []
    for line in lines:
        low = line.lower()
        if low.startswith("adet:"):
            started = True
            continue
        if started:
            if low.startswith(STOP_LINE_PREFIXES):
                break
            if low.startswith("sipariş") or low.startswith("alıcı adres"):
                continue
            title_lines.append(line)
    return clean_text(" ".join(title_lines))


def normalize_width(product_block: str) -> str:
    m = re.search(r"Width\s*:\s*([0-9.,]+\s*mm)", product_block, re.IGNORECASE)
    if m:
        return m.group(1).replace("mm", "MM").replace("Mm", "MM").strip()
    title = extract_product_title(product_block)
    m2 = re.search(r"\b([1-9]|10)\s*mm\b", title, re.IGNORECASE)
    if m2:
        return m2.group(0).replace("mm", "MM").strip()
    return ""


def normalize_size(product_block: str) -> str:
    m = re.search(r"Ring size\s*:\s*([^\n\r]+)", product_block, re.IGNORECASE)
    if not m:
        return ""
    raw = clean_text(strip_footer_noise(m.group(1)))
    m2 = re.search(r"(\d+(?:\s+\d+/\d+)?\s*US)", raw, re.IGNORECASE)
    return us_size_to_decimal(m2.group(1)) if m2 else us_size_to_decimal(raw)


def normalize_laser(product_block: str) -> str:
    lines = normalize_lines(product_block)
    laser_parts = []
    capture = False
    for line in lines:
        low = line.lower()
        if low.startswith("personalization"):
            capture = True
            piece = line.split(":", 1)[1].strip() if ":" in line else ""
            if piece:
                laser_parts.append(piece)
            continue
        if capture:
            if low.startswith(STOP_LINE_PREFIXES) or low.startswith("adet:"):
                break
            laser_parts.append(line)
    laser = clean_text(" ".join(laser_parts))
    laser = laser.replace('&quot;', '"').replace('quot;', '"').replace('""', '"')
    laser = laser.replace("Font 4-all caps initials", "")
    if laser.startswith(":"):
        laser = laser[1:].strip()
    laser = laser.replace('"', "")
    return clean_text(laser)


def detect_color(text: str) -> str:
    t = (text or "").lower()
    if "rose" in t or "pink" in t:
        return "ROSE"
    if "white gold" in t or "white" in t:
        return "BEYAZ"
    if "yellow gold" in t or "yellow" in t:
        return "SARI"
    return ""


def detect_shape(text: str) -> str:
    t = (text or "").lower()
    if "dome" in t:
        return "BOMBE"
    if "flat" in t:
        return "DÜZ"
    if "bevel" in t or "bevelled" in t or "beveled" in t:
        return "ÇATI"
    return ""


def detect_finish(text: str) -> str:
    t = (text or "").lower()
    return "MAT" if "matte" in t else ""


def detect_color_only(text: str) -> str:
    t = (text or "").lower()
    if "rose" in t or "pink" in t:
        return "ROSE"
    if "white gold" in t or "white" in t:
        return "BEYAZ"
    if "yellow gold" in t or "yellow" in t:
        return "SARI"
    return ""


def is_resize_listing(product_text: str) -> bool:
    t = (product_text or "").lower()
    return (
        "resizing service" in t
        or "ring resizing service" in t
        or "size adjustment for your order" in t
        or "resize listing" in t
        or "resizing" in t
    )


def build_model(product_title: str) -> str:
    low = (product_title or "").lower()
    if is_resize_listing(low):
        return "YENİLEME"
    if "oval solitaire ring" in low:
        return "OVAL TEKTAŞ"

    parts = []
    finish = detect_finish(product_title)
    shape = detect_shape(product_title)
    color = detect_color(product_title)

    if finish:
        parts.append(finish)
    if shape:
        parts.append(shape)
    if color:
        parts.append(color)

    return " ".join(parts).strip()


def build_product_hint(product_title: str) -> str:
    low = (product_title or "").lower()
    if is_resize_listing(low):
        return "Yüzük Yenileme"
    if "oval solitaire ring" in low:
        return "Oval Tektaş"
    return ""


def shorten_cerasus_product_name(title: str) -> str:
    t = html.unescape(clean_text(title))
    low = t.lower()

    if "arabic name necklace" in low:
        return "Arabic Name Necklace"
    if "bar pendant" in low or "name bar" in low:
        return "Bar Pendant Necklace"
    if "old english letter necklace" in low:
        return "Old English Letter Necklace"
    if "seagull necklace" in low:
        return "Seagull Necklace"
    if "bird charm necklace" in low:
        return "Bird Charm Necklace"
    if "opal ring" in low:
        return "Opal Ring"

    t = re.split(r"[•,\-]", t)[0]
    return truncate_text(t, 34)


def parse_page(page_text: str) -> List[Dict[str, str]]:
    customer = find_customer_name(page_text)
    order_no = extract_order_no(page_text)
    product_blocks = split_products(page_text)
    labels = []

    for block in product_blocks:
        title = extract_product_title(block)
        resize = is_resize_listing(block)
        width = "" if resize else normalize_width(block)
        size = normalize_size(block)
        laser = normalize_laser(block)
        model = build_model(title)
        note = "YENİLEME" if resize else ""
        urun_adi = build_product_hint(title)
        renk = "" if resize else detect_color_only(title)

        if model == "OVAL TEKTAŞ":
            width = ""

        labels.append({
            "magaza_adi": "CPNQ",
            "siparis_no": order_no,
            "musteri": customer,
            "genislik": width,
            "model": model,
            "olcu": size,
            "lazer": laser,
            "not": note,
            "urun_adi": urun_adi,
            "renk": renk,
            "sku": "",
            "urun": "",
            "zincir_boyu": "",
        })

    return labels


def parse_uploaded_pdf(pdf_bytes: bytes) -> List[Dict[str, str]]:
    all_labels = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "Sipariş Bilgileri" not in text:
                continue
            all_labels.extend(parse_page(text))
    return all_labels


def parse_ozellikler(text: str) -> Dict[str, List[str]]:
    result = {}
    if not text:
        return result

    text = html.unescape(text)
    pairs = re.findall(r"Ad:\s*([^,]+),\s*Değer:\s*([^,]+)", text, flags=re.IGNORECASE)
    for key, value in pairs:
        k = clean_text(key).lower()
        v = clean_text(value)
        result.setdefault(k, []).append(v)
    return result


def extract_widths_from_personalization(text: str) -> List[str]:
    if not text:
        return []
    widths = re.findall(r"(\d+(?:[.,]\d+)?)\s*mm", text, flags=re.IGNORECASE)
    cleaned = []
    for w in widths:
        w = w.replace(",", ".")
        if w.endswith(".0"):
            w = w[:-2]
        cleaned.append(f"{w}MM")
    return cleaned


def extract_cerasus_fields(row: Dict[str, str]) -> Dict[str, str]:
    urun_adi = html.unescape(row.get("ÜrünAdı", "") or "")
    ozellikler = html.unescape(row.get("Özellikler", "") or "")
    parsed = parse_ozellikler(ozellikler)

    zincir_boyu = first_nonempty(
        (parsed.get("necklace length") or [""])[0],
        (parsed.get("necklace lenght") or [""])[0],
    )

    renk = first_nonempty(
        (parsed.get("color") or [""])[0],
        (parsed.get("general material") or [""])[0],
        (parsed.get("material") or [""])[0],
        (parsed.get("band color") or [""])[0],
    )

    kisisellestirme = first_nonempty(
        (parsed.get("personalization") or [""])[0],
    )
    kisisellestirme = html.unescape(kisisellestirme).replace('"', "").strip()

    return {
        "urun": shorten_cerasus_product_name(urun_adi),
        "zincir_boyu": zincir_boyu,
        "renk": renk,
        "kisisellestirme": kisisellestirme,
        "sku": clean_text(row.get("Sku", "")),
    }


def parse_uploaded_csv(csv_bytes: bytes) -> List[Dict[str, str]]:
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    sample = text[:4096]

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        class SimpleDialect(csv.excel):
            delimiter = ","
        dialect = SimpleDialect

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []

    labels = []

    for raw_row in reader:
        row = {clean_text(k): clean_text(v) for k, v in raw_row.items() if k is not None}

        magaza_adi = row.get("MagazaAdı", "") or row.get("MağazaAdı", "") or "CPNQ"
        musteri = html.unescape(row.get("Alıcı", ""))
        siparis_no = row.get("SiparişNumarası", "")
        urun_adi = html.unescape(row.get("ÜrünAdı", "") or "")
        ozellikler = html.unescape(row.get("Özellikler", "") or "")

        # CERASUS İÇİN ÖZEL AKIŞ
        if "cerasus" in magaza_adi.lower():
            cerasus = extract_cerasus_fields(row)

            adet_raw = clean_text(str(row.get("Adet", "1")))
            try:
                adet = max(1, int(float(adet_raw)))
            except Exception:
                adet = 1

            for _ in range(adet):
                labels.append({
                    "magaza_adi": magaza_adi,
                    "siparis_no": siparis_no,
                    "musteri": musteri,
                    "sku": cerasus["sku"],
                    "urun": cerasus["urun"],
                    "zincir_boyu": cerasus["zincir_boyu"],
                    "renk": cerasus["renk"],
                    "lazer": cerasus["kisisellestirme"],
                    "not": "",
                    "genislik": "",
                    "model": "",
                    "olcu": "",
                    "urun_adi": urun_adi,
                })
            continue

        # DİĞER MAĞAZALAR İÇİN MEVCUT AKIŞ
        parsed = parse_ozellikler(ozellikler)

        ring_sizes = []
        if "ring size" in parsed:
            ring_sizes.extend(parsed["ring size"])
        if "size for you" in parsed:
            ring_sizes.extend([f"{parsed['size for you'][0]} US"])
        if "size for your partner" in parsed:
            ring_sizes.extend([f"{parsed['size for your partner'][0]} US"])

        ring_sizes = [us_size_to_decimal(x) for x in ring_sizes]

        widths = []
        if "width" in parsed:
            widths.extend([clean_text(x).replace("mm", "MM").replace("Mm", "MM") for x in parsed["width"]])

        personalization_values = parsed.get("personalization", [])
        lazer = personalization_values[0] if personalization_values else ""
        lazer = (
            html.unescape(lazer)
            .replace("&quot;", '"')
            .replace("quot;", '"')
            .replace('""', '"')
            .strip()
        )
        lazer = lazer.replace('"', "")

        if not widths and lazer:
            widths = extract_widths_from_personalization(lazer)

        model = build_model(urun_adi)
        note = ""
        resize = is_resize_listing(urun_adi) or is_resize_listing(ozellikler)
        renk = "" if resize else detect_color_only(urun_adi)

        if resize:
            model = "YENİLEME"
            note = "YENİLEME"
            widths = [""]
            if not ring_sizes:
                ring_sizes = [""]
        elif model == "OVAL TEKTAŞ":
            widths = [""]
            if not ring_sizes:
                ring_sizes = [""]
        else:
            if not widths:
                m = re.search(r"\b([1-9]|10)\s*mm\b", urun_adi, re.IGNORECASE)
                if m:
                    widths = [m.group(0).replace("mm", "MM")]
            if not ring_sizes:
                m = re.search(r"(\d+(?:\s+\d+/\d+)?\s*US)", ozellikler, re.IGNORECASE)
                if m:
                    ring_sizes = [us_size_to_decimal(m.group(1))]

        pair_mode = (
            "set of 2" in urun_adi.lower()
            or "his and her" in urun_adi.lower()
            or len(ring_sizes) >= 2
            or len(widths) >= 2
        )

        if pair_mode:
            count = max(len(ring_sizes), len(widths), 2)
            for i in range(count):
                labels.append({
                    "magaza_adi": magaza_adi,
                    "siparis_no": siparis_no,
                    "musteri": musteri,
                    "genislik": widths[i] if i < len(widths) else "",
                    "model": model,
                    "olcu": ring_sizes[i] if i < len(ring_sizes) else "",
                    "lazer": lazer,
                    "not": note,
                    "urun_adi": build_product_hint(urun_adi),
                    "renk": renk,
                    "sku": row.get("Sku", ""),
                    "urun": "",
                    "zincir_boyu": "",
                })
        else:
            labels.append({
                "magaza_adi": magaza_adi,
                "siparis_no": siparis_no,
                "musteri": musteri,
                "genislik": widths[0] if widths else "",
                "model": model,
                "olcu": ring_sizes[0] if ring_sizes else "",
                "lazer": lazer,
                "not": note,
                "urun_adi": build_product_hint(urun_adi),
                "renk": renk,
                "sku": row.get("Sku", ""),
                "urun": "",
                "zincir_boyu": "",
            })

    return [x for x in labels if any(str(v).strip() for v in x.values())]


def escape_paragraph_text(text: str) -> str:
    text = text or ""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def p(text: str, laser: bool = False) -> Paragraph:
    safe = escape_paragraph_text(text)
    if laser:
        return Paragraph(safe, LASER_STYLE)
    return Paragraph(safe, BASE_STYLE)


def make_label_table(item: Dict[str, str]) -> Table:
    magaza = item.get("magaza_adi", "CPNQ")

    if "cerasus" in magaza.lower():
        data = [
            [p("Mağaza"), p(magaza)],
            [p("Sipariş No"), p(item.get("siparis_no", ""))],
            [p("Müşteri"), p(item.get("musteri", ""))],
            [p("Ürün"), p(item.get("urun", ""))],
            [p("Zincir"), p(item.get("zincir_boyu", ""))],
            [p("Renk"), p(item.get("renk", ""))],
            [p("Not"), p(item.get("lazer", ""), laser=True)],
        ]

        row_heights = [
            0.34 * cm,
            0.34 * cm,
            0.42 * cm,
            0.52 * cm,
            0.34 * cm,
            0.34 * cm,
            0.70 * cm,
        ]

        t = Table(data, colWidths=[1.7 * cm, 4.3 * cm], rowHeights=row_heights)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.45, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 0.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
        ]))
        return t

    data = [
        [p("Mağaza Adı"), p(item.get("magaza_adi", "CPNQ"))],
        [p("Sipariş No"), p(item.get("siparis_no", ""))],
        [p("Müşteri Adı"), p(item.get("musteri", ""))],
        [p("Genişlik"), p(item.get("genislik", ""))],
        [p("Model"), p(item.get("model", ""))],
        [p("Ölçü"), p(item.get("olcu", ""))],
        [p("Lazer"), p(item.get("lazer", ""), laser=True)],
        [p("Not"), p(item.get("not", ""))],
    ]

    if not (item.get("musteri") or "").strip() and (item.get("urun_adi") or "").strip() and not (item.get("not") or "").strip():
        data[7][1] = p(item.get("urun_adi", ""))

    row_heights = [0.34 * cm, 0.34 * cm, 0.38 * cm, 0.30 * cm, 0.38 * cm, 0.30 * cm, 0.65 * cm, 0.45 * cm]

    t = Table(data, colWidths=[2.0 * cm, 4.0 * cm], rowHeights=row_heights)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.45, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
    ]))
    return t


def build_labels_pdf(labels: List[Dict[str, str]]) -> bytes:
    page_w, page_h = A4
    rows_per_page = int((page_h + ROW_GAP) // (LABEL_H + ROW_GAP))
    slots_per_page = rows_per_page * COLS

    usable_w = COLS * LABEL_W + (COLS - 1) * COL_GAP
    usable_h = rows_per_page * LABEL_H + (rows_per_page - 1) * ROW_GAP

    left_margin = (page_w - usable_w) / 2
    top_margin = (page_h - usable_h) / 2

    story = []

    for page_start in range(0, len(labels), slots_per_page):
        page_labels = labels[page_start:page_start + slots_per_page]
        grid = []
        idx = 0

        for r in range(rows_per_page):
            row = []
            for c in range(COLS):
                if idx < len(page_labels):
                    row.append(make_label_table(page_labels[idx]))
                    idx += 1
                else:
                    row.append("")
                if c < COLS - 1:
                    row.append("")
            grid.append(row)
            if r < rows_per_page - 1:
                grid.append([""] * (COLS * 2 - 1))

        col_widths = []
        for c in range(COLS):
            col_widths.append(LABEL_W)
            if c < COLS - 1:
                col_widths.append(COL_GAP)

        row_heights = []
        for r in range(rows_per_page):
            row_heights.append(LABEL_H)
            if r < rows_per_page - 1:
                row_heights.append(ROW_GAP)

        outer = Table(grid, colWidths=col_widths, rowHeights=row_heights)
        outer.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(outer)
        if page_start + slots_per_page < len(labels):
            story.append(PageBreak())

    if not story:
        story = [Paragraph("Etiket üretilemedi.", BASE_STYLE)]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left_margin,
        rightMargin=left_margin,
        topMargin=top_margin,
        bottomMargin=top_margin,
    )
    doc.build(story)
    return buffer.getvalue()


def production_model(model: str) -> str:
    m = (model or "").upper().strip()
    if "BOMBE" in m:
        return "BOMBE"
    if "DÜZ" in m:
        return "DÜZ"
    if "ÇATI" in m and "MAT" in m:
        return "ÇATI MAT"
    if "ÇATI" in m:
        return "ÇATI PARLAK"
    return ""


def mm_sort_key(value: str):
    text = (value or "").upper().replace("MM", "").strip()
    try:
        return float(text.replace(",", "."))
    except Exception:
        return 9999.0


def size_sort_key(value: str):
    text = clean_text(value)
    try:
        return float(text)
    except Exception:
        return 9999.0


def build_production_dataframe(labels: List[Dict[str, str]]) -> pd.DataFrame:
    rows = []
    for item in labels:
        rows.append({
            "Genişlik": item.get("genislik", ""),
            "Model": production_model(item.get("model", "")),
            "Ölçü": item.get("olcu", ""),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df[
        (df["Genişlik"].astype(str).str.strip() != "")
        | (df["Model"].astype(str).str.strip() != "")
        | (df["Ölçü"].astype(str).str.strip() != "")
    ].copy()
    df["_sort_mm"] = df["Genişlik"].apply(mm_sort_key)
    model_order = {"BOMBE": 1, "DÜZ": 2, "ÇATI MAT": 3, "ÇATI PARLAK": 4, "": 99}
    df["_sort_model"] = df["Model"].map(model_order).fillna(99)
    df["_sort_size"] = df["Ölçü"].apply(size_sort_key)
    df = df.sort_values(["_sort_mm", "_sort_model", "_sort_size"], kind="stable").drop(columns=["_sort_mm", "_sort_model", "_sort_size"])
    return df.reset_index(drop=True)


def build_personalization_dataframe(labels: List[Dict[str, str]]) -> pd.DataFrame:
    rows = []
    for item in labels:
        lazer = item.get("lazer", "")
        if str(lazer).strip():
            rows.append({
                "Müşteri Adı": truncate_text(item.get("musteri", ""), 28),
                "Genişlik": item.get("genislik", ""),
                "Model": production_model(item.get("model", "")),
                "Kişiselleştirme": clean_text(lazer),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.reset_index(drop=True)


def build_checklist_dataframe(labels: List[Dict[str, str]]) -> pd.DataFrame:
    rows = []
    for item in labels:
        rows.append({
            "Mağaza Adı": item.get("magaza_adi", "CPNQ"),
            "Sipariş No": item.get("siparis_no", ""),
            "Müşteri Adı": truncate_text(item.get("musteri", ""), 24),
            "Ürün": item.get("urun", ""),
            "Zincir": item.get("zincir_boyu", ""),
            "Renk": item.get("renk", ""),
            "Genişlik": item.get("genislik", ""),
            "Model": production_model(item.get("model", "")) if item.get("model", "") != "YENİLEME" else "YENİLEME",
            "Ölçü": item.get("olcu", ""),
            "Kişiselleştirme": truncate_text(item.get("lazer", ""), 30),
            "Check": "☐",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.reset_index(drop=True)


def build_production_summary(labels: List[Dict[str, str]]) -> pd.DataFrame:
    rows = []
    for item in labels:
        rows.append({
            "Genişlik": item.get("genislik", ""),
            "Model": production_model(item.get("model", "")),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df[
        (df["Genişlik"].astype(str).str.strip() != "")
        & (df["Model"].astype(str).str.strip() != "")
    ]

    summary = (
        df.groupby(["Genişlik", "Model"])
        .size()
        .reset_index(name="Adet")
    )

    summary["_sort_mm"] = summary["Genişlik"].apply(mm_sort_key)
    model_order = {"BOMBE": 1, "DÜZ": 2, "ÇATI MAT": 3, "ÇATI PARLAK": 4}
    summary["_sort_model"] = summary["Model"].map(model_order).fillna(99)

    summary = summary.sort_values(["_sort_mm", "_sort_model"]).drop(columns=["_sort_mm", "_sort_model"])
    return summary.reset_index(drop=True)


def dataframe_to_txt(df: pd.DataFrame, title: str) -> bytes:
    out = io.StringIO()

    out.write(f"{title}\n")
    out.write("=" * len(title) + "\n\n")

    if df.empty:
        out.write("Kayıt yok.\n")
        return out.getvalue().encode("utf-8")

    col_widths = {}
    for col in df.columns:
        max_len = max(df[col].astype(str).map(len).max(), len(col))
        col_widths[col] = max_len + 2

    header = ""
    for col in df.columns:
        header += col.ljust(col_widths[col])
    out.write(header + "\n")

    sep = ""
    for col in df.columns:
        sep += ("-" * (col_widths[col] - 1)) + " "
    out.write(sep + "\n")

    for _, row in df.iterrows():
        line = ""
        for col in df.columns:
            line += str(row[col]).ljust(col_widths[col])
        out.write(line + "\n")

    out.write("\n")
    return out.getvalue().encode("utf-8")


def personalization_df_to_txt(df: pd.DataFrame, title: str) -> bytes:
    out = io.StringIO()

    out.write(f"{title}\n")
    out.write("=" * len(title) + "\n\n")

    if df.empty:
        out.write("Kayıt yok.\n")
        return out.getvalue().encode("utf-8")

    name_w = 30
    width_w = 10
    model_w = 14

    for _, row in df.iterrows():
        musteri = truncate_text(str(row.get("Müşteri Adı", "")), name_w - 1)
        genislik = str(row.get("Genişlik", ""))
        model = truncate_text(str(row.get("Model", "")), model_w - 1)
        kisisellestirme = clean_text(str(row.get("Kişiselleştirme", "")))

        first_line = (
            musteri.ljust(name_w) +
            genislik.ljust(width_w) +
            model.ljust(model_w)
        )
        out.write(first_line.rstrip() + "\n")
        out.write(kisisellestirme + "\n")
        out.write("---------\n\n")

    return out.getvalue().encode("utf-8")

# ---------------------------------------------------
# ARAYÜZ
# ---------------------------------------------------
st.markdown("""
<div class="hero-box">
    <div class="hero-title">Etiket Hazırlama</div>
    <p class="hero-sub">CSV veya PDF dosyası yükleyin. Sistem etiketleri ve üretim dosyalarını otomatik hazırlasın.</p>
    <div class="step-strip">
        <div class="step-pill">1. Dosya yükle</div>
        <div class="step-pill">2. Kontrol et</div>
        <div class="step-pill">3. Çıktıları indir</div>
    </div>
</div>
""", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Sipariş dosyası yükleyin",
    type=["pdf", "csv"],
    help="Desteklenen formatlar: PDF ve CSV"
)

if uploaded is not None:
    file_bytes = uploaded.read()

    try:
        file_name = (uploaded.name or "").lower()

        with st.spinner("Dosya işleniyor..."):
            if file_name.endswith(".csv"):
                labels = parse_uploaded_csv(file_bytes)
                file_type = "CSV"
            else:
                labels = parse_uploaded_pdf(file_bytes)
                file_type = "PDF"

        if labels:
            magaza_adi = labels[0].get("magaza_adi", "CPNQ")
            df_production = build_production_dataframe(labels)
            df_personal = build_personalization_dataframe(labels)
            df_check = build_checklist_dataframe(labels)
            df_summary = build_production_summary(labels)

            output_pdf = build_labels_pdf(labels)
            txt_production = dataframe_to_txt(df_production, "Üretim Listesi")
            txt_personal = personalization_df_to_txt(df_personal, "Kişiselleştirme Listesi")
            txt_check = dataframe_to_txt(
                df_check,
                f"Mağaza Adı: {magaza_adi}\nKontrol Listesi"
            )
            txt_summary = dataframe_to_txt(df_summary, "Üretim Özeti")

            st.markdown('<div class="status-ok">Dosya başarıyla işlendi. Çıktılar indirilmeye hazır.</div>', unsafe_allow_html=True)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class="info-card">
                    <div class="info-label">Mağaza</div>
                    <div class="info-value">{magaza_adi}</div>
                </div>
                """, unsafe_allow_html=True)

            with c2:
                st.markdown(f"""
                <div class="info-card">
                    <div class="info-label">Dosya Türü</div>
                    <div class="info-value">{file_type}</div>
                </div>
                """, unsafe_allow_html=True)

            with c3:
                st.markdown(f"""
                <div class="info-card">
                    <div class="info-label">Toplam Etiket</div>
                    <div class="info-value">{len(labels)}</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown('<div class="section-title">Çıktıları İndir</div>', unsafe_allow_html=True)

            d1, d2 = st.columns(2)
            with d1:
                st.download_button(
                    "Etiket PDF indir",
                    data=output_pdf,
                    file_name="etiketler.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
                st.download_button(
                    "Kişiselleştirme listesi indir",
                    data=txt_personal,
                    file_name="kisisellestirme_listesi.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
                st.download_button(
                    "Üretim özeti indir",
                    data=txt_summary,
                    file_name="uretim_ozeti.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            with d2:
                st.download_button(
                    "Üretim listesi indir",
                    data=txt_production,
                    file_name="uretim_listesi.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
                st.download_button(
                    "Kontrol listesi indir",
                    data=txt_check,
                    file_name="kontrol_listesi.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            with st.expander("Detaylı önizleme", expanded=False):
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    "Etiketler",
                    "Üretim",
                    "Kişiselleştirme",
                    "Kontrol",
                    "Özet"
                ])

                with tab1:
                    st.dataframe(pd.DataFrame(labels), use_container_width=True, hide_index=True)

                with tab2:
                    st.dataframe(df_production, use_container_width=True, hide_index=True)

                with tab3:
                    st.dataframe(df_personal, use_container_width=True, hide_index=True)

                with tab4:
                    st.dataframe(df_check, use_container_width=True, hide_index=True)

                with tab5:
                    st.dataframe(df_summary, use_container_width=True, hide_index=True)

        else:
            st.warning("Dosyadan etiket oluşturulamadı. Dosya formatını veya içeriğini kontrol edin.")

    except Exception as e:
        st.error(f"Bir hata oluştu: {e}")

st.markdown('<div class="footer-note">Ekip kullanımı için sadeleştirilmiş etiket hazırlama ekranı</div>', unsafe_allow_html=True)
