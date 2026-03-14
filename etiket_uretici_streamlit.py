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

# --- KONFİGÜRASYON VE STİLLER ---
st.set_page_config(page_title="Etiket Üretici", page_icon="🏷️", layout="centered")

LABEL_W, LABEL_H = 6 * cm, 3 * cm
COLS = 3

# Font Kaydı
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
except:
    pass

BASE_STYLE = ParagraphStyle("base", fontName="DejaVuSans", fontSize=8, leading=8.5)
BOLD_STYLE = ParagraphStyle("bold", parent=BASE_STYLE, fontName="DejaVuSans-Bold")

ADDRESS_HINTS = [
    "street", "st ", "ave", "road", "house", "apt", "flat", "drive", "court", "park",
    "kentfield", "winston", "domain", "village", "barking", "ashburn", "buffalo"
]

STOP_WORDS = ["sipariş", "adet:", "geçildi", "stok", "ş", "ring size", "width", "personalization"]

# --- YARDIMCI ARAÇLAR ---

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def normalize_lines(text: str) -> List[str]:
    # Alt bilgi gürültülerini temizle
    text = re.sub(r"https?://\S+|Shipentegra|printmultipleorders", "", text, flags=re.IGNORECASE)
    return [clean_text(x) for x in text.splitlines() if clean_text(x)]

def is_stop_line(candidate: str) -> bool:
    low = candidate.lower()
    if re.search(r"\d{4}-\d{2}-\d{2}", candidate): return True
    if any(h in low for h in ADDRESS_HINTS): return True
    if any(sw in low for sw in STOP_WORDS): return True
    if re.search(r"\b(?:GB|US|IE)\b|\b[A-Z]{2}\d{4,}", candidate): return True
    return False

# --- VERİ AYIKLAMA ---

def find_customer_name(page_text: str) -> str:
    lines = normalize_lines(page_text)
    for i, line in enumerate(lines):
        if "Alıcı" in line:
            name_parts = []
            # Örn: Zara ve Jawando farklı satırlarda ise birleştir 
            for offset in range(1, 4):
                if i + offset < len(lines):
                    candidate = lines[i + offset]
                    if is_stop_line(candidate) or any(ch.isdigit() for ch in candidate):
                        break
                    name_parts.append(candidate)
            res = " ".join(name_parts).strip()
            if res: return res
    return ""

def normalize_size(block: str) -> str:
    # Kesirli ifadelerdeki ($) işaretlerini temizle 
    block_clean = block.replace("$", "")
    m = re.search(r"Ring size\s*:\s*([^$\n\r]+)", block_clean, re.IGNORECASE)
    if not m: return ""
    m2 = re.search(r"(\d+(?:\s+\d+/\d+)?\s*US)", m.group(1), re.IGNORECASE)
    return m2.group(1).upper().strip() if m2 else clean_text(m.group(1))

def build_model(title: str) -> str:
    t = title.lower()
    if "resizing service" in t: return "YENİLEME" # [cite: 135]
    if "oval solitaire" in t: return "OVAL TEKTAŞ" # [cite: 119]
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
    order_no = re.search(r"Sipariş Numarası\s*(\d+)", page_text, re.IGNORECASE)
    order_no = order_no.group(1) if order_no else ""
    
    # Adet bazlı ürün bloklarına ayır [cite: 8, 85]
    product_blocks = re.split(r"(?=Adet:\s*\d+)", page_text)
    labels = []
    for block in product_blocks:
        if "Adet:" not in block: continue
        title = clean_text(block.split("Adet:")[1]) # Basit başlık çekme
        is_resize = "resizing service" in title.lower()
        
        # Genişlik tespiti 
        width = ""
        w_match = re.search(r"Width\s*:\s*(\d+mm)", block, re.IGNORECASE)
        if w_match: width = w_match.group(1).upper()
        elif not is_resize: 
            w_match2 = re.search(r"(\d+mm)", title, re.IGNORECASE)
            if w_match2: width = w_match2.group(1).upper()

        labels.append({
            "siparis_no": order_no,
            "musteri": customer,
            "genislik": width,
            "model": build_model(title),
            "olcu": normalize_size(block),
            "lazer": clean_text(block.split("Personalization:")[1]) if "Personalization:" in block else "",
            "not": "YENİLEME" if is_resize else ("Oval Tektaş" if "oval" in title.lower() else "")
        })
    return labels

# --- PDF VE UI ---

def p(text: str, bold: bool = False) -> Paragraph:
    return Paragraph(str(text or ""), BOLD_STYLE if bold else BASE_STYLE)

def make_label_table(item: Dict[str, str]) -> Table:
    data = [
        [p("Sipariş No"), p(item["siparis_no"])],
        [p("Müşteri Adı"), p(item["musteri"], bold=True)],
        [p("Genişlik"), p(item["genislik"])],
        [p("Model"), p(item["model"])],
        [p("Ölçü"), p(item["olcu"])],
        [p("Lazer"), p(item["lazer"], bold=bool(item["lazer"]))],
        [p("Not"), p(item["not"])]
    ]
    t = Table(data, colWidths=[1.8*cm, 4.2*cm], rowHeights=[0.42*cm]*7)
    t.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.5, colors.black), ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    return t

def build_pdf(labels: List[Dict[str, str]]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, margin=0.5*cm)
    story = []
    grid = []
    # 3 sütunlu yapı oluştur
    for i in range(0, len(labels), 3):
        chunk = labels[i:i+3]
        row = [make_label_table(item) for item in chunk]
        while len(row) < 3: row.append("")
        grid.append(row)
    
    story.append(Table(grid, colWidths=[6.3*cm]*3, rowHeights=[3.2*cm]*len(grid)))
    doc.build(story)
    return buffer.getvalue()

st.title("🏷️ Etiket Üretici")
uploaded = st.file_uploader("PDF Yükle", type=["pdf"])

if uploaded:
    with pdfplumber.open(io.BytesIO(uploaded.read())) as pdf:
        all_data = []
        for page in pdf.pages:
            res = parse_page(page.extract_text() or "")
            all_data.extend(res)
    
    if all_data:
        st.success(f"{len(all_data)} etiket bulundu.")
        st.dataframe(all_data)
        st.download_button("PDF İndir", build_pdf(all_data), "etiketler.pdf")
