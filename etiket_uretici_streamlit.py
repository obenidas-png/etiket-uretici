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
    "street","st "," st","ave","avenue","road","rd","house","apt","apartment",
    "flat","dr","drive","cir","circle","prospect","domain","kentfield","winston",
    "valmont","central","augusta","village","park","cordova","barking","ashburn",
    "buffalo","new haven","austin","cookeville","belfast",
]

STOP_LINE_PREFIXES = (
    "ring size","width","personalization","gemstone type","shipping service","13.","https://","shipentegra"
)

def detect_store(text:str)->str:
    t=(text or "").lower()

    if "chepniq" in t:
        return "CPNQ"
    if "foria" in t:
        return "FRIA"
    if "cerasus" in t:
        return "CRSS"

    return "CPNQ"

def clean_text(text:str)->str:
    return re.sub(r"\s+"," ",text or "").strip()

def strip_footer_noise(text:str)->str:
    text=re.sub(r"https?://\S+","",text,flags=re.IGNORECASE)
    text=re.sub(r"\bShipentegra\b","",text,flags=re.IGNORECASE)
    return text

def normalize_lines(text:str)->List[str]:
    text=strip_footer_noise(text)
    return [clean_text(x) for x in text.splitlines() if clean_text(x)]

def extract_order_no(page_text:str)->str:
    m=re.search(r"Sipariş Numarası\s*(\d+)",page_text,re.IGNORECASE)
    return m.group(1).strip() if m else ""

def split_products(page_text:str)->List[str]:
    page_text=strip_footer_noise(page_text)
    parts=re.split(r"(?=Adet:\s*\d+)",page_text)
    return [p.strip() for p in parts if re.search(r"Adet:\s*\d+",p)]

def extract_product_title(block:str)->str:
    lines=normalize_lines(block)
    started=False
    title_lines=[]

    for line in lines:
        low=line.lower()

        if low.startswith("adet:"):
            started=True
            continue

        if started:
            if low.startswith(STOP_LINE_PREFIXES):
                break
            title_lines.append(line)

    return clean_text(" ".join(title_lines))

def detect_color_only(text:str)->str:
    t=(text or "").lower()

    if "rose" in t or "pink" in t:
        return "ROSE"
    if "white" in t:
        return "BEYAZ"
    if "yellow" in t:
        return "SARI"

    return ""

def build_model(title:str)->str:
    t=(title or "").lower()

    if "dome" in t:
        return "BOMBE"
    if "flat" in t:
        return "DÜZ"
    if "bevel" in t:
        return "ÇATI"

    return ""

def parse_page(page_text:str)->List[Dict[str,str]]:

    store=detect_store(page_text)

    order_no=extract_order_no(page_text)
    product_blocks=split_products(page_text)

    labels=[]

    for block in product_blocks:

        title=extract_product_title(block)

        labels.append({
            "siparis_no":order_no,
            "musteri":"",
            "genislik":"",
            "model":build_model(title),
            "olcu":"",
            "lazer":"",
            "not":"",
            "urun_adi":"",
            "renk":detect_color_only(title),
            "magaza":store
        })

    return labels

def parse_uploaded_pdf(pdf_bytes:bytes)->List[Dict[str,str]]:

    all_labels=[]

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:

        for page in pdf.pages:

            text=page.extract_text() or ""

            if "Sipariş Bilgileri" not in text:
                continue

            all_labels.extend(parse_page(text))

    return all_labels

def escape_paragraph_text(text:str)->str:
    text=text or ""
    text=text.replace("&","&amp;")
    text=text.replace("<","&lt;")
    text=text.replace(">","&gt;")
    return text

def p(text:str)->Paragraph:
    safe=escape_paragraph_text(text)
    return Paragraph(safe,BASE_STYLE)

def make_label_table(item:Dict[str,str])->Table:

    data=[
        [p("Mağaza Adı"),p(item.get("magaza",""))],
        [p("Sipariş No"),p(item.get("siparis_no",""))],
        [p("Müşteri Adı"),p(item.get("musteri",""))],
        [p("Genişlik"),p(item.get("genislik",""))],
        [p("Model"),p(item.get("model",""))],
        [p("Ölçü"),p(item.get("olcu",""))],
        [p("Lazer"),p(item.get("lazer",""))],
        [p("Not"),p(item.get("not",""))],
    ]

    row_heights=[0.34*cm]*8

    t=Table(data,colWidths=[2*cm,4*cm],rowHeights=row_heights)

    t.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.45,colors.black),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))

    return t

def build_labels_pdf(labels:List[Dict[str,str]])->bytes:

    page_w,page_h=A4

    rows_per_page=8
    slots_per_page=rows_per_page*COLS

    story=[]

    for page_start in range(0,len(labels),slots_per_page):

        page_labels=labels[page_start:page_start+slots_per_page]

        for item in page_labels:

            story.append(make_label_table(item))

        story.append(PageBreak())

    buffer=io.BytesIO()

    doc=SimpleDocTemplate(buffer,pagesize=A4)

    doc.build(story)

    return buffer.getvalue()

st.title("Etiket Üretici")

uploaded=st.file_uploader("Sipariş dosyası",type=["pdf"])

if uploaded is not None:

    file_bytes=uploaded.read()

    labels=parse_uploaded_pdf(file_bytes)

    st.write(f"Toplam etiket: {len(labels)}")

    if labels:

        st.dataframe(labels)

        store_name=labels[0].get("magaza","")

        st.markdown(f"**Mağaza Adı: {store_name}**")

        output_pdf=build_labels_pdf(labels)

        st.download_button(
            label="Etiket PDF indir",
            data=output_pdf,
            file_name="etiketler.pdf",
            mime="application/pdf",
        )

    else:

        st.warning("Dosya içinden etiket oluşturulamadı.")

st.caption("Streamlit Cloud üzerinde çalıştırmaya uygundur.")
