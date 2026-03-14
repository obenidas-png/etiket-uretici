import io
import re
from typing import List, Dict

import pdfplumber
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle, Spacer, PageBreak

st.set_page_config(page_title="Etiket Üretici", page_icon="🏷️", layout="centered")

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
    leading=8.5,
    spaceAfter=0,
    spaceBefore=0,
)

BOLD_STYLE = ParagraphStyle(
    "bold",
    parent=BASE_STYLE,
    fontName="DejaVuSans-Bold",
)

ADDRESS_HINTS = [
    "street", "st ", " st", "ave", "avenue", "road", "rd", "house", "apt", "apartment",
    "flat", "dr", "drive", "cir", "circle", "prospect", "domain", "kentfield", "winston",
    "prospect st", "valmont", "central ave", "augusta", "village", "park", "prospect", "cordova",
]

STOP_LINE_PREFIXES = (
    "ring size", "width", "personalization", "gemstone type", "shipping service", "13.", "https://", "shipentegra"
)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_footer_noise(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{1,2}/\d{1,2}\b", "", text)
    text = re.sub(r"\bShipentegra\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"printmultipleorders", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}\b", "", text)
    return text


def normalize_lines(text: str) -> List[str]:
    text = strip_footer_noise(text)
    lines = [clean_text(x) for x in text.splitlines() if clean_text(x)]
    return lines


def is_address_like(line: str) -> bool:
    low = line.lower()
    if any(h in low for h in ADDRESS_HINTS):
        return True
    if re.search(r"\b[A-Z]{2}\d{4,}", line):
        return True
    if re.search(r"\d{1,6}", line) and len(line.split()) >= 2:
        return True
    if re.search(r"\b(?:GB|US|IE)\b", line):
        return True
    return False


def extract_order_no(page_text: str) -> str:
    m = re.search(r"Sipariş Numarası\s*(\d+)", page_text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def find_customer_name(page_text: str) -> str:
    lines = normalize_lines(page_text)
    skip = {
        "Sipariş Bilgileri",
        "Alıcı Adres Sipariş Tarihi Kendi Notum",
        "Sipariş Numarası",
        "Sipariş Ürünleri",
    }
    for i, line in enumerate(lines):
        if line == "Alıcı Adres Sipariş Tarihi Kendi Notum":
            for candidate in lines[i + 1:i + 6]:
                if candidate in skip:
                    continue
                if re.search(r"\b\d{4}-\d{2}-\d{2}\b", candidate):
                    continue
                if candidate.isdigit():
                    continue
                if is_address_like(candidate):
                    continue
                if len(candidate.split()) >= 2:
                    return candidate
    # fallback: first reasonable person-like line before address/date
    for line in lines:
        if line in skip:
            continue
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", line):
            continue
        if is_address_like(line):
            continue
        if len(line.split()) >= 2 and not re.search(r"Sipariş|Adet:|Ring size|Width", line, re.IGNORECASE):
            return line
    return ""


def split_products(page_text: str) -> List[str]:
    page_text = strip_footer_noise(page_text)
    parts = re.split(r"(?=Adet:\s*\d+)", page_text)
    return [p.strip() for p in parts if re.search(r"Adet:\s*\d+", p)]


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
    return clean_text(strip_footer_noise(m.group(1))) if m else ""


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
            if line:
                laser_parts.append(line)
    laser = clean_text(" ".join(laser_parts))
    laser = laser.replace('"', "").replace("Font 4-all caps initials", "").strip()
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


def is_resize_listing(product_text: str) -> bool:
    t = (product_text or "").lower()
    return (
        "resizing service" in t
        or "ring resizing service" in t
        or "size adjustment for your order" in t
        or "resize listing" in t
    )


def build_model(product_title: str) -> str:
    lower = (product_title or "").lower()
    if is_resize_listing(lower):
        return "YENİLEME"
    if "oval solitaire ring" in lower:
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
            # Skip pure footer/date remnants
            if low.startswith("sipariş") or low.startswith("alıcı adres"):
                continue
            title_lines.append(line)
    title = clean_text(" ".join(title_lines))
    return title


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

        # Avoid gemstone size being mistaken as width for non-band items
        if "oval tektaş" in model.lower() or "oval solitaire" in title.lower():
            width = ""

        labels.append({
            "siparis_no": order_no,
            "musteri": customer,
            "genislik": width,
            "model": model,
            "olcu": size,
            "lazer": laser,
            "not": note,
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


def p(text: str, bold: bool = False) -> Paragraph:
    safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, BOLD_STYLE if bold else BASE_STYLE)


def make_label_table(item: Dict[str, str]) -> Table:
    lazer_bold = bool((item.get("lazer") or "").strip())
    data = [
        [p("Sipariş No"), p(item.get("siparis_no", ""))],
        [p("Müşteri Adı"), p(item.get("musteri", ""))],
        [p("Genişlik"), p(item.get("genislik", ""))],
        [p("Model"), p(item.get("model", ""))],
        [p("Ölçü"), p(item.get("olcu", ""))],
        [p("Lazer"), p(item.get("lazer", ""), bold=lazer_bold)],
        [p("Not"), p(item.get("not", ""))],
    ]

    row_heights = [0.40 * cm, 0.42 * cm, 0.35 * cm, 0.42 * cm, 0.35 * cm, 0.53 * cm, 0.53 * cm]
    t = Table(data, colWidths=[2.0 * cm, 4.0 * cm], rowHeights=row_heights)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.45, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
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


st.title("Etiket Üretici")
st.write("Sipariş PDF dosyasını yükleyin. Sistem etiketleri otomatik üretip PDF olarak indirmenizi sağlar.")

uploaded = st.file_uploader("Sipariş PDF", type=["pdf"])

with st.expander("Kurallar", expanded=False):
    st.markdown(
        """
- 3 sütunlu A4 yerleşim
- Etiket boyutu: 6 × 3 cm
- Etiketler arasında boşluk
- dome → bombe
- flat → düz
- beveled → çatı
- matte → mat
- yellow → sarı
- white → beyaz
- rose/pink → rose
- Aynı siparişte 2 ürün varsa 2 etiket
- Lazer varsa kalın yazılır
- Resize listing için Model ve Not: YENİLEME
        """
    )

if uploaded is not None:
    pdf_bytes = uploaded.read()
    try:
        labels = parse_uploaded_pdf(pdf_bytes)
        st.subheader("Önizleme")
        st.write(f"Toplam etiket: {len(labels)}")
        if labels:
            st.dataframe(labels, use_container_width=True)
            output_pdf = build_labels_pdf(labels)
            st.download_button(
                label="Etiket PDF indir",
                data=output_pdf,
                file_name="etiketler.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.warning("PDF içinden etiket oluşturulamadı.")
    except Exception as e:
        st.error(f"Bir hata oluştu: {e}")

st.caption("Streamlit Cloud üzerinde çalıştırmaya uygundur.")
