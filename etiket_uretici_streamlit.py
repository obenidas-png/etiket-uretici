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

LABEL_W = 6.2 * cm
LABEL_H = 3.2 * cm
COLS = 3

# Font Kaydı
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
except:
    pass

# Stil Tanımları - Leading (satır aralığı) artırıldı
BASE_STYLE = ParagraphStyle("base", fontName="DejaVuSans", fontSize=7.5, leading=9)
BOLD_STYLE = ParagraphStyle("bold", parent=BASE_STYLE, fontName="DejaVuSans-Bold")

# --- VERİ İŞLEME ARAÇLARI ---

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def normalize_lines(text: str) -> List[str]:
    # Alt bilgi ve teknik gürültüleri temizle
    text = re.sub(r"https?://\S+|Shipentegra|printmultipleorders|\d{1,2}/\d{1,2}", "", text, flags=re.IGNORECASE)
    return [clean_text(x) for x in text.splitlines() if clean_text(x)]

def find_customer_name(page_text: str) -> str:
    lines = normalize_lines(page_text)
    # Shipentegra PDF'inde isimler genellikle "Alıcı" kelimesinden hemen sonraki satırlarda gelir 
    for i, line in enumerate(lines):
        if "Alıcı" in line:
            name_parts = []
            for offset in range(1, 4):
                if i + offset < len(lines):
                    candidate = lines[i + offset]
                    # Tarih, Adres (Street, Ave) veya Posta kodu görünce dur 
                    if re.search(r"\d{4}-\d{2}-\d{2}|street|ave|road|dr\b|\b[A-Z]{2}\d+", candidate, re.IGNORECASE):
                        break
                    if candidate and not any(ch.isdigit() for ch in candidate):
                        name_parts.append(candidate)
            return " ".join(name_parts).strip()
    return ""

def normalize_size(block: str) -> str:
    # Kesirli ölçülerdeki ($) işaretini temizler [cite: 15, 29, 63]
    clean_block = block.replace("$", "")
    m = re.search(r"Ring size\s*:\s*([^$\n\r]+)", clean_block, re.IGNORECASE)
    if not m: return ""
    # "8 1/4 US" gibi formatları yakalar [cite: 15]
    m2 = re.search(r"(\d+(?:\s+\d+/\d+)?\s*US)", m.group(1), re.IGNORECASE)
    return m2.group(1).upper().strip() if m2 else clean_text(m.group(1))

def build_model(title: str) -> str:
    t = title.lower()
    if "resizing service" in t: return "YENİLEME" # [cite: 135]
    if "oval solitaire" in t: return "OVAL TEKTAŞ" # [cite: 119]
    parts = []
    if "matte" in t: parts.append("MAT") # [cite: 9]
    if "bevel" in t: parts.append("ÇATI") # [cite: 9]
    elif "dome" in t: parts.append("BOMBE") # [cite: 26]
    elif "flat" in t: parts.append("DÜZ") # [cite: 58]
    if "white" in t: parts.append("BEYAZ") # [cite: 9]
    elif "yellow" in t: parts.append("SARI") # [cite: 27]
    elif "rose" in t or "pink" in t: parts.append("ROSE")
    return " ".join(parts).strip()

def parse_page(page_text: str) -> List[Dict[str, str]]:
    customer = find_customer_name(page_text)
    order_no = re.search(r"Sipariş Numarası\s*(\d+)", page_text, re.IGNORECASE)
    order_no = order_no.group(1) if order_no else ""
    
    # Adet: ifadesini ayraç olarak kullan [cite: 8, 25, 41]
    product_blocks = re.split(r"(?=Adet:\s*\d+)", page_text)
    labels = []
    for block in product_blocks:
        if "Adet:" not in block: continue
        # Başlık Adet:'den sonraki ilk satırdır
        title = normalize_lines(block.split("Adet:")[1])[0] if "Adet:" in block else ""
        is_resize = "resizing service" in title.lower()
        
        # Genişlik tespiti [cite: 10, 30, 46]
        width = ""
        w_match = re.search(r"Width\s*:\s*(\d+mm)", block, re.IGNORECASE)
        if w_match: width = w_match.group(1).upper()
        elif not is_resize:
            w_match2 = re.search(r"(\d+mm)", block, re.IGNORECASE)
            if w_match2: width = w_match2.group(1).upper()

        labels.append({
            "siparis_no": order_no,
            "musteri": customer,
            "genislik": width,
            "model": build_model(block),
            "olcu": normalize_size(block),
            "lazer": clean_text(block.split("Personalization:")[1].split("\n")[0]) if "Personalization:" in block else "", # [cite: 31, 64]
            "not": "YENİLEME" if is_resize else ("Oval Tektaş" if "oval" in title.lower() else "")
        })
    return labels

# --- PDF OLUŞTURMA ---

def p(text: str, bold: bool = False) -> Paragraph:
    safe_text = str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe_text, BOLD_STYLE if bold else BASE_STYLE)

def make_label_table(item: Dict[str, str]) -> Table:
    # Hücre içindeki üst üste binmeyi engellemek için yükseklikler artırıldı
    data = [
        [p("Sipariş No"), p(item["siparis_no"])],
        [p("Müşteri Adı"), p(item["musteri"], bold=True)],
        [p("Genişlik"), p(item["genislik"])],
        [p("Model"), p(item["model"])],
        [p("Ölçü"), p(item["olcu"])],
        [p("Lazer"), p(item["lazer"], bold=bool(item["lazer"]))],
        [p("Not"), p(item["not"])]
    ]
    # Sütun genişlikleri: 1.8cm ve 4.2cm (Toplam 6cm)
    # Satır yükseklikleri: Toplam 3.2cm olacak şekilde dengelendi
    t = Table(data, colWidths=[1.9 * cm, 4.1 * cm], rowHeights=[0.45 * cm] * 7)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t

def build_pdf(labels: List[Dict[str, str]]) -> bytes:
    buffer = io.BytesIO()
    # Kenar boşlukları ayarlandı
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.4*cm, rightMargin=0.4*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    story = []
    
    grid = []
    for i in range(0, len(labels), 3):
        chunk = labels[i:i+3]
        row = [make_label_table(item) for item in chunk]
        while len(row) < 3: row.append("") # Boşlukları doldur
        grid.append(row)
    
    # Ana tablo oluşturulurken etiketler arası boşluk için padding eklendi
    main_table = Table(grid, colWidths=[6.3 * cm] * 3, rowHeights=[3.3 * cm] * len(grid))
    main_table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    
    story.append(main_table)
    doc.build(story)
    return buffer.getvalue()

# --- STREAMLIT ARAYÜZÜ ---

st.title("🏷️ Etiket Üretici")
uploaded = st.file_uploader("Shipentegra PDF Dosyasını Buraya Yükleyin", type=["pdf"])

if uploaded:
    with pdfplumber.open(io.BytesIO(uploaded.read())) as pdf:
        all_labels = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_labels.extend(parse_page(text))
    
    if all_labels:
        st.success(f"✅ {len(all_labels)} Adet Etiket Oluşturuldu.")
        st.dataframe(all_labels)
        pdf_bytes = build_pdf(all_labels)
        st.download_button(
            label="📥 Etiketleri PDF Olarak İndir",
            data=pdf_bytes,
            file_name="hazir_etiketler.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    else:
        st.warning("PDF içerisinde uygun sipariş verisi bulunamadı.")
