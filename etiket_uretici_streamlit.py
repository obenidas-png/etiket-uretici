import io
import math
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
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

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


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_whitespace_keep_lines(text: str) -> List[str]:
    return [clean_text(x) for x in (text or "").splitlines() if clean_text(x)]


def extract_order_no(text: str) -> str:
    m = re.search(r"Sipariş Numarası\s*\n?\s*(\d+)", text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def find_customer_name(page_text: str) -> str:
    lines = normalize_whitespace_keep_lines(page_text)
    if not lines:
        return ""

    skip_prefixes = {
        "Sipariş Bilgileri",
        "Alıcı Adres Sipariş Tarihi Kendi Notum",
        "Sipariş Numarası",
        "Sipariş Ürünleri",
    }

    for i, line in enumerate(lines):
        if line == "Alıcı Adres Sipariş Tarihi Kendi Notum":
            for candidate in lines[i + 1:i + 4]:
                if candidate in skip_prefixes:
                    continue
                if re.search(r"\b\d{4}-\d{2}-\d{2}\b", candidate):
                    continue
                if candidate.isdigit():
                    continue
                if "Shipentegra" in candidate or "http" in candidate:
                    continue
                if len(candidate.split()) >= 2:
                    return candidate
    return ""


def split_products(page_text: str) -> List[str]:
    parts = re.split(r"(?=Adet:\s*\d+)", page_text)
    return [clean_text(p) for p in parts if "Adet:" in p]


def normalize_width(product_block: str) -> str:
    m = re.search(r"Width\s*:\s*([0-9.,]+\s*mm)", product_block, re.IGNORECASE)
    if m:
        return m.group(1).replace("mm", "MM").replace("Mm", "MM").strip()

    m2 = re.search(r"\b([1-9]|10)\s*mm\b", product_block, re.IGNORECASE)
    if m2:
        return m2.group(0).replace("mm", "MM").strip()
    return ""


def normalize_size(product_block: str) -> str:
    m = re.search(r"Ring size\s*:\s*([^\n\r]+)", product_block, re.IGNORECASE)
    return clean_text(m.group(1)) if m else ""


def normalize_laser(product_block: str) -> str:
    m = re.search(
        r"Personalization\s*:\s*([^\n\r]+(?:\n(?!Adet:|Ring size|Width|Gemstone type|Shipping Service|13\.)[^\n\r]+)*)",
        product_block,
        re.IGNORECASE,
    )
    if not m:
        return ""
    laser = clean_text(m.group(1))
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
    if "bevel" in t or "beveled" in t or "bevelled" in t:
        return "ÇATI"
    return ""


def detect_finish(text: str) -> str:
    t = (text or "").lower()
    if "matte" in t:
        return "MAT"
    return ""


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
    lines = normalize_whitespace_keep_lines(block)
    started = False
    title_lines = []
    stop_starts = (
        "Ring size",
        "Width",
        "Personalization",
        "Gemstone type",
        "Shipping Service",
    )

    for line in lines:
        if line.startswith("Adet:"):
            started = True
            continue
        if started:
            if any(line.startswith(x) for x in stop_starts):
                break
            title_lines.append(line)

    return clean_text(" ".join(title_lines))


def parse_page(page_text: str) -> List[Dict[str, str]]:
    customer = find_customer_name(page_text)
    order_no = extract_order_no(page_text)
    product_blocks = split_products(page_text)
    labels = []

    for block in product_blocks:
        title = extract_product_title(block)
        resize = is_resize_listing(block)
        label = {
            "siparis_no": order_no,
            "musteri": customer,
            "genislik": "" if resize else normalize_width(block),
            "model": build_model(title),
            "olcu": normalize_size(block),
            "lazer": normalize_laser(block),
            "not": "YENİLEME" if resize else "",
        }
        labels.append(label)

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
    return Paragraph(text or "", BOLD_STYLE if bold else BASE_STYLE)


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
- Resize listing için Not alanı: YENİLEME
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
