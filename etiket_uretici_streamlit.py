import io
import re
import csv
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
    "valmont", "central", "augusta", "village", "park", "cordova", "barking", "ashburn",
    "buffalo", "new haven", "austin", "cookeville", "belfast",
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
    return m2.group(1).upper().replace("  ", " ").strip() if m2 else raw


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
    laser = laser.replace('&quot;', '"').replace('quot;', '"').replace('"', '')
    laser = laser.replace("Font 4-all caps initials", "")
    if laser.startswith(":"):
        laser = laser[1:].strip()
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

        if model == "OVAL TEKTAŞ":
            width = ""

        labels.append({
            "siparis_no": order_no,
            "musteri": customer,
            "genislik": width,
            "model": model,
            "olcu": size,
            "lazer": laser,
            "not": note,
            "urun_adi": urun_adi,
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

        musteri = row.get("Alıcı", "")
        siparis_no = row.get("SiparişNumarası", "")
        urun_adi = row.get("ÜrünAdı", "")
        ozellikler = row.get("Özellikler", "")
        adet = row.get("Adet", "1")

        parsed = parse_ozellikler(ozellikler)

        ring_sizes = []
        if "ring size" in parsed:
            ring_sizes.extend(parsed["ring size"])
        if "size for you" in parsed:
            ring_sizes.extend([f"{parsed['size for you'][0]} US"])
        if "size for your partner" in parsed:
            ring_sizes.extend([f"{parsed['size for your partner'][0]} US"])

        ring_sizes = [clean_text(x).upper() for x in ring_sizes]

        widths = []
        if "width" in parsed:
            widths.extend([clean_text(x).replace("mm", "MM").replace("Mm", "MM") for x in parsed["width"]])

        personalization_values = parsed.get("personalization", [])
        lazer = personalization_values[0] if personalization_values else ""
        lazer = lazer.replace('“', '').replace('”', '').replace('"', '').strip()

        # set of 2 listinglerinde personalization içinden width çek
        if not widths and lazer:
            widths = extract_widths_from_personalization(lazer)

        model = build_model(urun_adi)
        note = ""
        resize = is_resize_listing(urun_adi) or is_resize_listing(ozellikler)

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
                    ring_sizes = [m.group(1).upper()]

        # Çoklu ürün mantığı
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
                    "siparis_no": siparis_no,
                    "musteri": musteri,
                    "genislik": widths[i] if i < len(widths) else "",
                    "model": model,
                    "olcu": ring_sizes[i] if i < len(ring_sizes) else "",
                    "lazer": lazer,
                    "not": note,
                    "urun_adi": build_product_hint(urun_adi),
                })
        else:
            labels.append({
                "siparis_no": siparis_no,
                "musteri": musteri,
                "genislik": widths[0] if widths else "",
                "model": model,
                "olcu": ring_sizes[0] if ring_sizes else "",
                "lazer": lazer,
                "not": note,
                "urun_adi": build_product_hint(urun_adi),
            })

    return [x for x in labels if any(str(v).strip() for v in x.values())]


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

    if not (item.get("musteri") or "").strip() and (item.get("urun_adi") or "").strip() and not (item.get("not") or "").strip():
        data[6][1] = p(item.get("urun_adi", ""))

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
st.write("Sipariş PDF veya CSV dosyasını yükleyin. Sistem etiketleri otomatik üretip PDF olarak indirmenizi sağlar.")

uploaded = st.file_uploader("Sipariş dosyası", type=["pdf", "csv"])

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
- CSV yüklenirse müşteri adı ve diğer alanlar doğrudan kolonlardan okunur
        """
    )

if uploaded is not None:
    file_bytes = uploaded.read()
    try:
        file_name = (uploaded.name or "").lower()

        if file_name.endswith(".csv"):
            labels = parse_uploaded_csv(file_bytes)
            file_type = "CSV"
        else:
            labels = parse_uploaded_pdf(file_bytes)
            file_type = "PDF"

        st.subheader("Önizleme")
        st.write(f"Toplam etiket: {len(labels)}")
        st.write(f"Dosya türü: {file_type}")

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
            st.warning("Dosya içinden etiket oluşturulamadı.")
    except Exception as e:
        st.error(f"Bir hata oluştu: {e}")

st.caption("Streamlit Cloud üzerinde çalıştırmaya uygundur.")
