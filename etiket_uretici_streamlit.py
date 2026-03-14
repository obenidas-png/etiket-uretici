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
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle, PageBreak

# --- KONFİGÜRASYON ---
st.set_page_config(page_title="Etiket Üretici", page_icon="🏷️", layout="centered")

LABEL_W = 6 * cm
LABEL_H = 3 * cm
COLS = 3
COL_GAP = 0.5 * cm
ROW_GAP = 0.5 * cm

# Font yolları (Lokalde çalıştırıyorsan dosyaların aynı klasörde olduğundan emin ol)
FONT_REGULAR = "DejaVuSans.ttf" 
FONT_BOLD = "DejaVuSans-Bold.ttf"

# Sistemde font yoksa varsayılanlara düşmemesi için kontrol (Hata alırsan font dosyalarını proje klasörüne koy)
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
except:
    pass # Fontlar bulunamazsa standart fontlara düşer

BASE_STYLE = ParagraphStyle(
    "base",
    fontName="DejaVuSans",
    fontSize=8,
    leading=8.5,
)

BOLD_STYLE = ParagraphStyle(
    "bold",
    parent=BASE_STYLE,
    fontName="DejaVuSans-Bold",
)

ADDRESS_HINTS = [
    "street", "st ", " st", "ave", "avenue", "road", "rd", "house", "apt", "apartment",
    "flat", "dr", "drive", "cir", "circle", "prospect", "domain", "kentfield", "winston",
    "valmont", "central", "augusta", "village", "park", "cordova", "barking", "ashburn",
    "buffalo", "new haven", "austin", "cookeville", "belfast",
]

STOP_LINE_PREFIXES = (
    "ring size", "width", "personalization", "gemstone type", "shipping service", "https://", "shipentegra"
)

# --- YARDIMCI FONKSİYONLAR ---

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def strip_footer_noise(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bShipentegra\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"printmultipleorders", "", text, flags=re.IGNORECASE)
    return text

def normalize_lines(text: str) -> List[str]:
    text = strip_footer_noise(text)
    return [clean_text(x) for x in text.splitlines() if clean_text(x)]

def is_stop_line(candidate: str) -> bool:
    low = candidate.lower()
    # Tarih, Adres ipuçları veya Sipariş başlıkları ismi durdurur
    if re.search(r"\d{4}-\d{2}-\d{2}", candidate): return True
    if any(h in low for h in ADDRESS_HINTS): return True
    if any(x in low for x in ["sipariş", "adet:", "geçeildi", "stok", "ş"]): return True
    if re.search(r"\b(?:GB|US|IE)\b", candidate): return True
    return False

# --- VERİ ÇEKME MANTIĞI ---

def find_customer_name(page_text: str) -> str:
    lines = normalize_lines(page_text)
    
    for i, line in enumerate(lines):
        # PDF'deki tablo başlığını yakala
        if "Alıcı" in line:
            name_parts = []
            # Başlıktan sonraki satırları kontrol et, isim ve soyismi birleştir
            for offset in range(1, 4):
                if i + offset < len(lines):
                    candidate = lines[i + offset].strip()
                    if is_stop_line(candidate) or any(ch.isdigit() for ch in candidate):
                        break
                    name_parts.append(candidate)
            
            full_name = " ".join(name_parts).strip()
            if full_name:
                return full_name
    return ""

def extract_order_no(page_text: str) -> str:
    m = re.search(r"Sipariş Numarası\s*(\d+)", page_text, re.IGNORECASE)
    return m.group(1).strip() if m else ""

def split_products(page_text: str) -> List[str]:
    parts = re.split(r"(?=Adet:\s*\d+)", page_text)
    return [p.strip() for p in parts if re.search(r"Adet:\s*\d+", p)]

def extract_product_title(block: str) -> str:
    lines = normalize_lines(block)
    started = False
    title_lines = []
    for line in lines:
        if line.lower().startswith("adet:"):
            started = True
            continue
        if started:
            if line.lower().startswith(STOP_LINE_PREFIXES): break
            title_lines.append(line)
    return clean_text(" ".join(title_lines))

def normalize_width(product_block: str) -> str:
    m = re.search(r"Width\s*:\s*([0-9.,]+\s*mm)", product_block, re.IGNORECASE)
    if m: return m.group(1).upper().strip()
    title = extract_product_title(product_block)
    m2 = re.search(r"\b([1-9]|10)\s*mm\b", title, re.IGNORECASE)
    return m2.group(0).upper().strip() if m2 else ""

def normalize_size(product_block: str) -> str:
    # Kesirli ölçüleri ($1/4$) temizleyerek yakalar
    m = re.search(r"Ring size\s*:\s*([^$\n\r]+)", product_block.replace("$", ""), re.IGNORECASE)
    if not m: return ""
    raw = clean_text(m.group(1))
    m2 = re.search(r"(\d+(?:\s+\d+/\d+)?\s*US)", raw, re.IGNORECASE)
    return m2.group(1).upper().strip() if m2 else raw

def normalize_laser(product_block: str) -> str:
    if "Personalization" not in product_block: return ""
    lines = normalize_lines(product_block)
    laser_parts = []
    capture = False
    for line in lines:
        if "personalization" in line.lower():
            capture = True
            if ":" in line: laser_parts.append(line.split(":", 1)[1])
            continue
        if capture:
            if any(line.lower().startswith(x) for x in STOP_LINE_PREFIXES) or "adet:" in line.lower(): break
            laser_parts.append(line)
    res = clean_text(" ".join(laser_parts)).replace("&quot;", '"').replace('"', '')
    return res if "Font 4" not in res else res.split("initials")[-1].strip()

def build_model(title: str) -> str:
    t = title.lower()
    if "resizing service" in t: return "YENİLEME"
    if "oval solitaire" in t: return "OVAL TEKTAŞ"
    
    parts = []
    if "matte" in t: parts.append("MAT")
    if "dome" in t: parts.append("BOMBE")
    elif "flat" in t: parts.append("DÜZ")
    elif "bevel" in t: parts.append("ÇATI")
    
    if "white" in t: parts.append("BEYAZ")
    elif "yellow" in t: parts.append("SARI")
    elif "rose" in t or "pink" in t: parts.append("ROSE")
    
    return " ".join(parts).strip()

def parse_page(page_text: str) -> List[Dict[str, str]]:
    customer = find_customer_name(page_text)
    order_no = extract_order_no(page_text)
    product_blocks = split_products(page_text)
    labels = []

    for block in product_blocks:
        title = extract_product_title(block)
        resize = "resizing service" in title.lower()
        labels.append({
            "siparis_no": order_no,
            "musteri": customer,
            "genislik": "" if resize else normalize_width(block),
            "model": build_model(title),
            "olcu": normalize_size(block),
            "lazer": normalize_laser(block),
            "not": "YENİLEME" if resize else ("Oval Tektaş" if "oval" in title.lower() else ""),
        })
    return labels

# --- PDF OLUŞTURMA VE UI ---

def make_label_table(item: Dict[str, str]) -> Table:
    lazer_bold = bool(item.get("lazer", "").strip())
    data = [
        [p("Sipariş No"), p(item["siparis_no"])],
        [p("Müşteri Adı"), p(item["musteri"], bold=True)],
        [p("Genişlik"), p(item["genislik"])],
        [p("Model"), p(item["model"])],
        [p("Ölçü"), p(item["olcu"])],
        [p("Lazer"), p(item["lazer"], bold=lazer_bold)],
        [p("Not"), p(item["not"])],
    ]
    t = Table(data, colWidths=[2.0 * cm, 4.0 * cm], rowHeights=[0.4*cm]*5 + [0.5*cm]*2)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t

def build_labels_pdf(labels: List[Dict[str, str]]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.5*cm, rightMargin=0.5*cm, topMargin=1*cm, bottomMargin=1*cm)
    story = []
    
    # Etiketleri 3 sütunlu tabloya diz
    grid = []
    for i in range(0, len(labels), 3):
        row_items = labels[i:i+3]
        row = [make_label_
