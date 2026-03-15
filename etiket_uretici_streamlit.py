import io
import re
import csv
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

st.set_page_config(page_title="Etiket Üretici", page_icon="🏷️", layout="centered")

LABEL_W = 6 * cm
LABEL_H = 3 * cm
COLS = 3
COL_GAP = 0.5 * cm
ROW_GAP = 0.5 * cm

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

if "DejaVuSans" not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_REGULAR))

BASE_STYLE = ParagraphStyle(
    "base",
    fontName="DejaVuSans",
    fontSize=8,
    leading=8.3,
)

def detect_store(text: str) -> str:

    t = (text or "").lower()

    if "chepniq" in t:
        return "CPNQ"

    if "foria" in t:
        return "FRIA"

    if "cerasus" in t:
        return "CRSS"

    return "CPNQ"


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_page(page_text: str) -> List[Dict[str, str]]:

    store = detect_store(page_text)

    m = re.search(r"Sipariş Numarası\s*(\d+)", page_text)
    order_no = m.group(1) if m else ""

    blocks = re.split(r"(?=Adet:\s*\d+)", page_text)

    labels = []

    for block in blocks:

        if "Adet:" not in block:
            continue

        labels.append({
            "siparis_no": order_no,
            "musteri": "",
            "genislik": "",
            "model": "",
            "olcu": "",
            "lazer": "",
            "not": "",
            "magaza": store
        })

    return labels


def parse_uploaded_pdf(pdf_bytes: bytes) -> List[Dict[str, str]]:

    all_labels = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:

        for page in pdf.pages:

            text = page.extract_text() or ""

            if "Sipariş" not in text:
                continue

            all_labels.extend(parse_page(text))

    return all_labels


def parse_uploaded_csv(csv_bytes: bytes) -> List[Dict[str, str]]:

    text = csv_bytes.decode("utf-8-sig", errors="replace")

    reader = csv.DictReader(io.StringIO(text))

    labels = []

    for row in reader:

        urun = row.get("ÜrünAdı", "")

        store = detect_store(urun)

        labels.append({
            "siparis_no": row.get("SiparişNumarası", ""),
            "musteri": row.get("Alıcı", ""),
            "genislik": "",
            "model": "",
            "olcu": "",
            "lazer": "",
            "not": "",
            "magaza": store
        })

    return labels


def escape_paragraph_text(text: str) -> str:

    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    return text


def p(text: str) -> Paragraph:
    return Paragraph(escape_paragraph_text(text), BASE_STYLE)


def make_label_table(item: Dict[str, str]) -> Table:

    data = [

        [p("Mağaza Adı"), p(item.get("magaza", ""))],
        [p("Sipariş No"), p(item.get("siparis_no", ""))],
        [p("Müşteri Adı"), p(item.get("musteri", ""))],
        [p("Genişlik"), p(item.get("genislik", ""))],
        [p("Model"), p(item.get("model", ""))],
        [p("Ölçü"), p(item.get("olcu", ""))],
        [p("Lazer"), p(item.get("lazer", ""))],
        [p("Not"), p(item.get("not", ""))],

    ]

    t = Table(data, colWidths=[2 * cm, 4 * cm])

    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    return t


def build_labels_pdf(labels: List[Dict[str, str]]) -> bytes:

    story = []

    for item in labels:

        story.append(make_label_table(item))
        story.append(PageBreak())

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=A4)

    doc.build(story)

    return buffer.getvalue()


st.title("Etiket Üretici")

uploaded = st.file_uploader("Sipariş dosyası", type=["pdf", "csv"])


if uploaded is not None:

    file_bytes = uploaded.read()

    file_name = uploaded.name.lower()

    if file_name.endswith(".csv"):

        labels = parse_uploaded_csv(file_bytes)
        file_type = "CSV"

    else:

        labels = parse_uploaded_pdf(file_bytes)
        file_type = "PDF"

    st.subheader("Önizleme")

    st.write(f"Dosya türü: {file_type}")
    st.write(f"Toplam etiket: {len(labels)}")

    if labels:

        st.dataframe(labels)

        store_name = labels[0].get("magaza", "")

        st.markdown(f"**Mağaza Adı: {store_name}**")

        output_pdf = build_labels_pdf(labels)

        st.download_button(
            label="Etiket PDF indir",
            data=output_pdf,
            file_name="etiketler.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    else:

        st.warning("Dosya içinden etiket oluşturulamadı.")


st.caption("Streamlit Cloud üzerinde çalıştırmaya uygundur.")
