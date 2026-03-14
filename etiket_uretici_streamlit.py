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

# --- SAYFA VE FONT AYARLARI ---
st.set_page_config(page_title="Etiket Üretici", page_icon="🏷️", layout="centered")

LABEL_W = 6.2 * cm
LABEL_H = 3.2 * cm
COLS = 3

# Fontları kaydet (Font dosyalarının sistemde yüklü olduğunu varsayarsak)
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
except:
    pass

# Stil ayarları (Çakışmayı önlemek için leading değeri düşürüldü)
BASE_STYLE = ParagraphStyle("base", fontName="DejaVuSans", fontSize=7.5, leading=8)
BOLD_STYLE = ParagraphStyle("bold", parent=BASE_STYLE, fontName="DejaVuSans-Bold")

# --- VERİ İŞLEME FONKSİYONLARI ---

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def find_customer_name(page_text: str) -> str:
    """PDF tablosundaki parçalı isimleri birleştirir."""
    lines = [clean_text(l) for l in page_text.splitlines() if clean_text(l)]
    for i, line in enumerate(lines):
        if "Alıcı" in line:
            name_parts = []
            for offset in range(1, 4):
                if i + offset < len(lines):
                    candidate = lines[i + offset]
                    # Tarih veya adres satırına geldiysek dur
                    if re.search(r"\d{4}-\d{2}-\d{2}|street|ave|road|house|barking|ashburn|buffalo|austin|cookeville|belfast", candidate, re.IGNORECASE):
                        break
                    if not any(ch.isdigit() for ch in candidate):
                        name_parts.append(candidate)
            return " ".join(name_parts).strip()
    return ""

def parse_product_block(block: str) -> Dict:
    """Tek bir ürün bloğundan detayları ayıklar."""
    title = clean_text(block.split("\n")[0])
    is_resize = "resizing service" in title.lower()
    
    # Model tespiti
    model = "YENİLEME" if is_resize else ""
    if "oval solitaire" in title.lower(): model = "OVAL TEKTAŞ"
    else:
        m_parts = []
        if "matte" in title.lower(): m_parts.append("MAT")
        if "bevel" in title.lower(): m_parts.append("ÇATI")
        elif "dome" in title.lower(): m_parts.append("BOMBE")
        elif "flat" in title.lower(): m_parts.append("DÜZ")
        if "white" in title.lower(): m_parts.append("BEYAZ")
        elif "yellow" in title.lower(): m_parts.append("SARI")
        elif "rose" in title.lower() or "pink" in title.lower(): m_parts.append("ROSE")
        if not model: model = " ".join(m_parts).strip()

    # Ölçü ve Genişlik
    size = ""
    size_match = re.search(r"Ring size:\s*([\d\s/]+US)", block.replace("$", ""), re.IGNORECASE)
    if size_match: size = size_match.group(1).strip()
    
    width = ""
    width_match = re.search(r"(\d+mm)", block, re.IGNORECASE)
    if width_match: width = width_match.group(1).upper()

    # Lazer
    lazer = ""
    if "Personalization:" in block:
        lazer = clean_text(block.split("Personalization:")[1].split("https")[0])
        lazer = lazer.replace("&quot;", "").replace("Font 4-all caps initials", "").strip()

    return {
        "model": model,
        "olcu": size,
        "genislik": "" if is_resize or "oval" in title.lower() else width,
        "lazer": lazer,
        "not": "YENİLEME" if is_resize else ("Oval Tektaş" if "oval" in title.lower() else "")
    }

def parse_pdf(pdf_bytes: bytes) -> List[Dict]:
    extracted_labels = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text or "Sipariş Bilgileri" not in text: continue
            
            customer = find_customer_name(text)
            order_no = re.search(r"Sipariş Numarası\s*(\d+)", text)
            order_no = order_no.group(1) if order_no else ""
            
            # Ürünleri Adet: 1 ibaresinden ayır
            parts = re.split(r"Adet:\s*\d+", text)
            for part in parts[1:]: # İlk parça başlık kısmıdır
                details = parse_product_block(part)
                details.update({"siparis_no": order_no, "musteri": customer})
                extracted_labels.append(details)
    return extracted_labels

# --- PDF TABLO OLUŞTURMA ---

def p(text: str, bold: bool = False) -> Paragraph:
    return Paragraph(str(text or ""), BOLD_STYLE if bold else BASE_STYLE)

def make_label_cell(item: Dict) -> Table:
    data = [
        [p("Sipariş No"), p(item["siparis_no"])],
        [p("Müşteri Adı"), p(item["musteri"], bold=True)],
        [p("Genişlik"), p(item["genislik"])],
        [p("Model"), p(item["model"])],
        [p("Ölçü"), p(item["olcu"])],
        [p("Lazer"), p(item["lazer"], bold=bool(item["lazer"]))],
        [p("Not"), p(item["not"])]
    ]
    # Sabit satır yükseklikleri çakışmayı önler
    t = Table(data, colWidths=[1.8 * cm, 4.0 * cm], rowHeights=[0.42 * cm] * 7)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t

def create_final_pdf(labels: List[Dict]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, margin=0.5*cm)
    story = []
    
    grid = []
    for i in range(0, len(labels), 3):
        row = [make_label_cell(item) for item in labels[i:i+3]]
        while len(row) < 3: row.append("") 
        grid.append(row)
    
    main_table = Table(grid, colWidths=[6.3 * cm] * 3, rowHeights=[3.3 * cm] * len(grid))
    story.append(main_table)
    doc.build(story)
    return buffer.getvalue()

# --- STREAMLIT UI ---

st.title("🏷️ Gelişmiş Etiket Üretici")
file = st.file_uploader("Shipentegra PDF Yükle", type="pdf")

if file:
    labels = parse_pdf(file.read())
    if labels:
        st.write(f"✅ {len(labels)} etiket hazırlandı.")
        st.dataframe(labels)
        pdf_out = create_final_pdf(labels)
        st.download_button("📥 Etiketleri PDF İndir", pdf_out, "etiketler.pdf", "application/pdf")
