"""
ETSY ATÖLYE YÖNETİM SİSTEMİ - Streamlit Uygulaması
CSV veya XLSX Yükle → PDF Etiket + 3 TXT Listesi Oluştur
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, HexColor
import re

st.set_page_config(page_title="Sipariş Takip Sistemi", page_icon="🏭", layout="wide")

st.markdown("""
<style>
    .main-title {
        text-align: center; padding: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px; color: white; margin-bottom: 30px;
    }
    .stButton>button { width: 100%; background-color: #667eea; color: white; font-weight: bold; }

    /* Dosya yükleme alanı */
    [data-testid="stFileUploader"] {
        background-color: #fff4e6;
        border: 2px dashed #ff8c00;
        border-radius: 12px;
        padding: 20px;
    }
    [data-testid="stFileUploader"] label {
        font-size: 1.2rem !important;
        font-weight: bold !important;
        color: #cc6600 !important;
    }
    [data-testid="stFileUploadDropzone"] {
        background-color: #fff4e6 !important;
    }
    section[data-testid="stFileUploadDropzone"] > div {
        color: #cc6600 !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-title">🏭 Sipariş Takip Sistemi Sistemi</h1>', unsafe_allow_html=True)


def xlsx_to_standard_df(df_xlsx):
    rows = []
    for _, row in df_xlsx.iterrows():
        ozellikler_parts = []
        for i in range(1, 4):
            name = row.get(f'Options Name {i}')
            value = row.get(f'Options Value {i}')
            if pd.notna(name) and pd.notna(value):
                ozellikler_parts.append(f"Ad:{name}, Değer:{value}")
        ozellikler = ", ".join(ozellikler_parts)
        buyer_note = str(row.get('Notes - From Buyer', '') or '')
        rows.append({
            'MagazaAdı':       row.get('Market - Store Name', ''),
            'SiparişNumarası': row.get('Order - Number', ''),
            'Alıcı':           row.get('Ship To - Name', ''),
            'ÜrünAdı':         row.get('Item - Name', ''),
            'Özellikler':      ozellikler if ozellikler else None,
            '_BuyerNote':      buyer_note,
            '_GiftMessage':    str(row.get('Gift - Message', '') or ''),
            '_ShipBy':         str(row.get('Date - Ship By Date', '') or ''),
            '_OrderTotal':     row.get('Amount - Order Total', ''),
        })
    return pd.DataFrame(rows)


def load_file(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith('.xlsx') or name.endswith('.xlsm'):
        df_raw = pd.read_excel(uploaded_file, engine='openpyxl')
        return xlsx_to_standard_df(df_raw), 'xlsx'
    else:
        return pd.read_csv(uploaded_file), 'csv'


def parse_csv(df):
    orders = []

    def get_store_code(store_name):
        store_lower = str(store_name).lower()
        if 'foria' in store_lower: return 'FRY'
        elif 'chepniq' in store_lower: return 'CPQ'
        elif 'cerasus' in store_lower: return 'CRSS'
        else: return store_name[:4].upper()

    for idx, row in df.iterrows():
        store_name = str(row.get('MagazaAdı', ''))
        store_code = get_store_code(store_name)
        product = str(row.get('ÜrünAdı', ''))
        product_lower = product.lower()

        if any(keyword in product_lower for keyword in [
            'price adjustment', 'shipping fee', 'shipping cost', 'additional fee', 'extra charge'
        ]):
            continue

        props = {}
        if pd.notna(row.get('Özellikler')):
            parts = str(row['Özellikler']).split(',')
            for i in range(0, len(parts), 2):
                if i + 1 < len(parts):
                    key = parts[i].replace('Ad:', '').strip()
                    value = parts[i + 1].replace('Değer:', '').strip()
                    props[key] = value

        if row.get('_BuyerNote'):
            props.setdefault('Personalization', row['_BuyerNote'])

        if 'cerasus' in store_name.lower():
            product_clean = product.split(' - ')[0]
            if len(product_clean) > 40:
                product_clean = product_clean[:37] + "..."
            color = props.get('Metal', '')
            if not color:
                if '14k yellow gold' in product_lower or 'yellow gold' in product_lower: color = '14K Yellow Gold'
                elif '14k white gold' in product_lower or 'white gold' in product_lower: color = '14K White Gold'
                elif '14k rose gold' in product_lower or 'rose gold' in product_lower: color = '14K Rose Gold'
                elif 'sterling silver' in product_lower or 'silver' in product_lower: color = 'Sterling Silver'
            orders.append({'Mağaza': store_code, 'Sipariş No': row.get('SiparişNumarası', ''),
                'Müşteri': row.get('Alıcı', ''), 'Genişlik': '', 'Renk': color, 'Model': '',
                'Ölçü': '', 'Kişiselleştirme': props.get('Personalization', ''), 'Ürün': product_clean})
        else:
            model = ''
            color = ''
            width = props.get('Width', props.get('Band Width', ''))
            if 'white gold' in product_lower or 'beyaz' in product_lower: color = 'BEYAZ'
            elif 'yellow gold' in product_lower or 'sarı' in product_lower or 'gold filled' in product_lower: color = 'SARI'
            if 'resizing' in product_lower or 'size adjustment' in product_lower or 'replacement' in product_lower: model = 'YENİLEME'
            elif 'bevel' in product_lower: model = 'ÇATI MAT' if ('matte' in product_lower or 'mat' in product_lower) else 'ÇATI'
            elif 'dome' in product_lower: model = 'BOMBE'
            elif 'flat' in product_lower: model = 'DÜZ'
            elif 'oval' in product_lower or 'solitaire' in product_lower: model = 'OVAL TEKTAŞ'
            if not width:
                width_match = re.search(r'(\d+)\s*mm', product_lower)
                if width_match: width = width_match.group(1) + 'MM'
            else:
                width = str(width).strip()
                width = width.upper() if 'mm' in width.lower() else width.upper() + 'MM'
            ring_size = props.get('Ring size', props.get('Size for You', ''))
            if 'set of 2' in product_lower or 'Size for Your Partner' in props:
                size1 = props.get('Size for You', '')
                size2 = props.get('Size for Your Partner', '')
                width1, width2 = '2MM', '4MM'
                personalization = props.get('Personalization', '')
                if personalization:
                    pers_lower = personalization.lower()
                    hers_match = re.search(r'hers[^:]*:\s*(\d+)\s*mm', pers_lower)
                    his_match = re.search(r'his[^:]*:\s*(\d+)\s*mm', pers_lower)
                    if hers_match: width1 = hers_match.group(1) + 'MM'
                    if his_match: width2 = his_match.group(1) + 'MM'
                if width1 == '2MM' or width2 == '4MM':
                    if 'hers' in product_lower and 'his' in product_lower:
                        hers_match = re.search(r'hers[^:]*:\s*(\d+)\s*mm', product_lower)
                        his_match = re.search(r'his[^:]*:\s*(\d+)\s*mm', product_lower)
                        if hers_match: width1 = hers_match.group(1) + 'MM'
                        if his_match: width2 = his_match.group(1) + 'MM'
                    elif '2mm' in product_lower and '4mm' in product_lower: width1, width2 = '2MM', '4MM'
                    elif width: width1 = width2 = width
                if size1:
                    orders.append({'Mağaza': store_code, 'Sipariş No': row.get('SiparişNumarası', ''),
                        'Müşteri': row.get('Alıcı', ''), 'Genişlik': width1, 'Renk': color, 'Model': model,
                        'Ölçü': size1, 'Kişiselleştirme': props.get('Personalization', ''), 'Ürün': product})
                if size2:
                    orders.append({'Mağaza': store_code, 'Sipariş No': row.get('SiparişNumarası', ''),
                        'Müşteri': row.get('Alıcı', ''), 'Genişlik': width2, 'Renk': color, 'Model': model,
                        'Ölçü': size2, 'Kişiselleştirme': props.get('Personalization', ''), 'Ürün': product})
            else:
                orders.append({'Mağaza': store_code, 'Sipariş No': row.get('SiparişNumarası', ''),
                    'Müşteri': row.get('Alıcı', ''), 'Genişlik': width.upper() if width else '',
                    'Renk': color, 'Model': model.upper() if model else '', 'Ölçü': ring_size,
                    'Kişiselleştirme': props.get('Personalization', ''), 'Ürün': product})

    # Aynı sipariş numarasına ait birden fazla sipariş varsa "coklu" işaretle
    siparis_sayilari = pd.Series([o['Sipariş No'] for o in orders])
    tekrar_edenler = set(siparis_sayilari[siparis_sayilari.duplicated(keep=False)].tolist())
    for o in orders:
        o['Çoklu'] = o['Sipariş No'] in tekrar_edenler

    return pd.DataFrame(orders)


def turkce_to_ascii(text):
    if not text or pd.isna(text): return ''
    text = str(text)
    for a, b in {'ı':'i','İ':'I','ş':'s','Ş':'S','ğ':'g','Ğ':'G','ü':'u','Ü':'U','ö':'o','Ö':'O','ç':'c','Ç':'C'}.items():
        text = text.replace(a, b)
    return text


def create_pdf_labels(orders_df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    label_width, label_height = 5 * cm, 3 * cm
    margin_x, margin_y = 0.2 * cm, 0.2 * cm
    gap_x, gap_y = 0.15 * cm, 0.15 * cm
    labels_per_row, labels_per_column = 4, 9
    labels_per_page = labels_per_row * labels_per_column
    label_count = 0

    for idx, row in orders_df.iterrows():
        col = label_count % labels_per_row
        row_num = (label_count // labels_per_row) % labels_per_column
        if label_count > 0 and label_count % labels_per_page == 0:
            c.showPage()
        x = margin_x + (col * (label_width + gap_x))
        y = page_height - margin_y - ((row_num + 1) * (label_height + gap_y))
        draw_label(c, x, y, label_width, label_height, row)
        label_count += 1

    c.save()
    buffer.seek(0)
    return buffer


def draw_label(c, x, y, width, height, data):
    c.setStrokeColor(black)
    c.setLineWidth(1)
    c.rect(x, y, width, height)
    text_x = x + 0.1 * cm
    font_size = 7
    store = str(data.get('Mağaza', '')).lower()
    coklu = data.get('Çoklu', False)
    line_height = height / 7

    for i in range(1, 7):
        c.setLineWidth(0.3)
        c.line(x, y + (i * line_height), x + width, y + (i * line_height))

    if 'cerasus' in store or store == 'crss':
        note = ''
        if pd.notna(data.get('Kişiselleştirme')):
            note = str(data['Kişiselleştirme']).replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
            note = turkce_to_ascii(note[:30])
        coklu_label = ' (COKLU SIPARIS)' if coklu else ''
        rows = [
            ('Magaza', 'CRSS' + coklu_label),
            ('Siparis No', str(data['Sipariş No'])),
            ('Musteri', turkce_to_ascii(str(data['Müşteri'])[:20])),
            ('Urun', turkce_to_ascii(str(data['Ürün'])[:25])),
            ('Zincir', ''),
            ('Renk', turkce_to_ascii(str(data['Renk'])[:15])),
            ('Not', note)
        ]
    else:
        pers_text = ''
        if pd.notna(data['Kişiselleştirme']):
            pers_text = str(data['Kişiselleştirme']).replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')[:30]
        coklu_label = ' (COKLU SIPARIS)' if coklu else ''
        rows = [
            ('Magaza', str(data.get('Mağaza', 'CPQ')) + coklu_label),
            ('Siparis No', str(data['Sipariş No'])),
            ('Musteri Adi', turkce_to_ascii(str(data['Müşteri'])[:25])),
            ('Genislik', str(data['Genişlik'])),
            ('Model', turkce_to_ascii(f"{data['Model']} {data['Renk']}".strip())),
            ('Olcu', str(data['Ölçü'])),
            ('Lazer', pers_text)
        ]

    for i, (label, value) in enumerate(rows):
        row_y = y + height - ((i + 0.65) * line_height)
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(text_x, row_y, label)
        c.setFont("Helvetica", font_size - 1)
        try: c.drawString(x + 1.7 * cm, row_y, str(value))
        except: c.drawString(x + 1.7 * cm, row_y, turkce_to_ascii(str(value)))


def create_lazer_labels(orders_df):
    """Kişiselleştirmesi olan siparişler için ayrı lazer etiket PDF'i"""
    personalized = orders_df[
        orders_df['Kişiselleştirme'].notna() &
        (orders_df['Kişiselleştirme'] != '') &
        (orders_df['Kişiselleştirme'] != 'nan')
    ].copy()

    if len(personalized) == 0:
        return None

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    label_width, label_height = 9.5 * cm, 4.5 * cm
    margin_x, margin_y = 0.5 * cm, 0.5 * cm
    gap_x, gap_y = 0.3 * cm, 0.3 * cm
    labels_per_row, labels_per_column = 2, 6
    labels_per_page = labels_per_row * labels_per_column
    label_count = 0

    for idx, row in personalized.iterrows():
        col = label_count % labels_per_row
        row_num = (label_count // labels_per_row) % labels_per_column
        if label_count > 0 and label_count % labels_per_page == 0:
            c.showPage()
        x = margin_x + (col * (label_width + gap_x))
        y = page_height - margin_y - ((row_num + 1) * (label_height + gap_y))
        draw_lazer_label(c, x, y, label_width, label_height, row)
        label_count += 1

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def draw_lazer_label(c, x, y, width, height, data):
    """Sadece müşteri adı, genişlik ve kişiselleştirme metni olan lazer etiketi"""
    c.setStrokeColor(HexColor('#ff8c00'))
    c.setLineWidth(1.5)
    c.rect(x, y, width, height)

    font_size = 8
    label_col_w = 2.0 * cm
    text_x = x + 0.2 * cm

    pers = str(data.get('Kişiselleştirme', ''))
    pers = pers.replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
    pers_ascii = turkce_to_ascii(pers)

    # Başlık
    c.setFillColor(HexColor('#cc6600'))
    c.setFont("Helvetica-Bold", font_size + 1)
    c.drawString(text_x, y + height - 0.5 * cm, "LAZER ETIKETI")
    c.setFillColor(black)

    # Ayırıcı çizgi
    c.setStrokeColor(HexColor('#ff8c00'))
    c.setLineWidth(0.8)
    c.line(x, y + height - 0.7 * cm, x + width, y + height - 0.7 * cm)

    # Müşteri
    row_y = y + height - 1.1 * cm
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Musteri:")
    c.setFont("Helvetica", font_size)
    c.drawString(text_x + label_col_w, row_y, turkce_to_ascii(str(data.get('Müşteri', ''))[:35]))

    # Genişlik
    row_y -= 0.6 * cm
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Genislik:")
    c.setFont("Helvetica", font_size)
    c.drawString(text_x + label_col_w, row_y, str(data.get('Genişlik', '')))

    # Kişiselleştirme — satırlara böl
    row_y -= 0.6 * cm
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Lazer:")

    # Her satırda yaklaşık kaç karakter sığar
    chars_per_line = int((width - label_col_w - 0.4 * cm) / (font_size * 0.52))
    c.setFont("Helvetica", font_size)
    line_start = 0
    max_lines = 4
    for line_i in range(max_lines):
        chunk = pers_ascii[line_start:line_start + chars_per_line]
        if not chunk:
            break
        lx = text_x + label_col_w if line_i == 0 else text_x + 0.3 * cm
        c.drawString(lx, row_y - (line_i * 0.52 * cm), chunk)
        line_start += chars_per_line


def create_uretim_listesi(orders_df):
    production = orders_df[orders_df['Model'] != 'YENİLEME'].copy()
    output = "Üretim Listesi\n==============\n\n"
    output += f"{'Genişlik':<10}{'Model':<15}{'Ölçü':<15}\n"
    output += f"{'-'*9} {'-'*14} {'-'*14}\n"
    for _, row in production.iterrows():
        output += f"{row['Genişlik']:<10}{row['Model']:<15}{row['Ölçü']:<15}\n"
    return output


def create_kisisellestime_listesi(orders_df):
    personalized = orders_df[
        orders_df['Kişiselleştirme'].notna() &
        (orders_df['Kişiselleştirme'] != '') &
        (orders_df['Kişiselleştirme'] != 'nan')
    ].copy()
    if len(personalized) == 0:
        return "Kişiselleştirme gerektiren sipariş yok."
    output = "Kişiselleştirme Listesi\n=======================\n\n"
    for _, row in personalized.iterrows():
        text = str(row['Kişiselleştirme']).replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&').replace('\\n', '\n   ')
        output += f"Müşteri: {row['Müşteri']}\nGenişlik: {row['Genişlik']}\nKişiselleştirme:\n   {text}\n" + "-" * 80 + "\n\n"
    return output


def create_kontrol_listesi(orders_df, store_name=''):
    def tr(text):
        if not text or str(text) == 'nan': return ''
        text = str(text)
        for a, b in {'ı':'i','İ':'I','ş':'s','Ş':'S','ğ':'g','Ğ':'G','ü':'u','Ü':'U','ö':'o','Ö':'O','ç':'c','Ç':'C'}.items():
            text = text.replace(a, b)
        return text

    buffer = io.BytesIO()
    page_w, page_h = landscape(A4)
    margin = 1 * cm
    usable_w = page_w - 2 * margin

    col_ratios = [0.12, 0.16, 0.07, 0.07, 0.09, 0.09, 0.34, 0.06]
    col_labels = ['Siparis No', 'Musteri Adi', 'Genislik', 'Renk', 'Model', 'Olcu', 'Kisisellestime', 'CHECK']
    col_widths = [usable_w * r for r in col_ratios]

    n = len(orders_df)
    if n <= 15:   font_size, row_h = 8, 1.0 * cm
    elif n <= 25: font_size, row_h = 7, 0.85 * cm
    elif n <= 40: font_size, row_h = 6, 0.72 * cm
    else:         font_size, row_h = 5.5, 0.65 * cm

    header_h = row_h * 1.3
    c = canvas.Canvas(buffer, pagesize=landscape(A4))

    def draw_header(y_start):
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", font_size + 1)
        c.drawString(margin, y_start + 0.3 * cm, tr("Magaza: " + str(store_name) + "  |  Kontrol Listesi"))
        y = y_start - 0.1 * cm
        c.setFillColor(HexColor("#444444"))
        c.rect(margin, y - header_h, usable_w, header_h, fill=1, stroke=0)
        c.setFillColor(HexColor("#ffffff"))
        c.setFont("Helvetica-Bold", font_size)
        x = margin
        for label, w in zip(col_labels, col_widths):
            c.drawString(x + 3, y - header_h + 4, label)
            x += w
        c.setFillColor(black)
        return y - header_h

    top_y = page_h - margin - 0.6 * cm
    y = draw_header(top_y)

    for i, (_, row) in enumerate(orders_df.iterrows()):
        if y - row_h < margin:
            c.showPage()
            y = draw_header(page_h - margin - 0.6 * cm)

        if i % 2 == 0:
            c.setFillColor(HexColor("#f5f5f5"))
            c.rect(margin, y - row_h, usable_w, row_h, fill=1, stroke=0)
            c.setFillColor(black)

        pers = ''
        if pd.notna(row['Kişiselleştirme']):
            pers = str(row['Kişiselleştirme']).replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&').replace('\\n', ' ')

        vals = [
            str(row['Sipariş No']),
            tr(str(row['Müşteri'])),
            str(row['Genişlik']),
            tr(str(row['Renk'])),
            tr(str(row['Model'])),
            str(row['Ölçü']),
            tr(pers),
            '[ ]'
        ]

        c.setFont("Helvetica", font_size)
        x = margin
        for val, w in zip(vals, col_widths):
            max_chars = int(w / (font_size * 0.58))
            c.drawString(x + 3, y - row_h + 4, val[:max_chars])
            x += w

        c.setStrokeColor(HexColor("#cccccc"))
        c.setLineWidth(0.3)
        c.line(margin, y - row_h, margin + usable_w, y - row_h)
        c.setStrokeColor(black)
        y -= row_h

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# ── Ana uygulama ──────────────────────────────
st.markdown("""
<div style="max-width: 700px; margin: 0 auto 30px auto;">
""", unsafe_allow_html=True)

col_l, col_mid, col_r = st.columns([1, 3, 1])
with col_mid:
    st.markdown("### 📂 Sipariş Dosyası Yükle")
    uploaded_file = st.file_uploader(
        "📦 Dosyayı buraya sürükleyin veya tıklayın",
        type=['csv', 'xlsx', 'xlsm'],
        help="ShipEntegra: Siparişler > İndir (Excel) seçilerek indirilen dosyayı yükleyin"
    )

st.markdown("</div>", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])
with col2:
    st.markdown("### ℹ️ Bilgi")
    st.info("""
    **Dosya nasıl alınır?**
    ShipEntegra sitesinden
    **Siparişler > İndir (Excel)**
    seçilerek dosya yüklenecek.

    ---
    **Desteklenen formatlar:**
    - 📊 ShipEntegra Excel (.xlsx)
    - 📄 Etsy CSV export

    **Oluşacak Dosyalar:**
    - 📄 PDF Etiketler
    - 🟠 Lazer Etiketleri (PDF)
    - 📝 Üretim Listesi
    - 📝 Kişiselleştirme Listesi
    - 📄 Kontrol Listesi (PDF)
    """)

if uploaded_file:
    with col1:
        try:
            if 'last_file_name' not in st.session_state or st.session_state.get('last_file_name') != uploaded_file.name:
                st.session_state['files_created'] = False
                st.session_state['last_file_name'] = uploaded_file.name

            df, file_type = load_file(uploaded_file)

            if file_type == 'xlsx':
                st.success(f"✅ XLSX: {len(df)} satır yüklendi!")
            else:
                st.success(f"✅ CSV: {len(df)} ham sipariş yüklendi!")

            with st.spinner("Siparişler işleniyor..."):
                orders_df = parse_csv(df)

            st.success(f"✅ {len(orders_df)} sipariş işlendi!")

            with st.expander("📋 İşlenmiş Siparişler"):
                st.dataframe(orders_df)

            st.markdown("### 📊 Özet")
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Toplam Sipariş", len(orders_df))
            with c2: st.metric("Kişiselleştirme", orders_df['Kişiselleştirme'].notna().sum())
            with c3: st.metric("Farklı Model", orders_df['Model'].nunique())
            with c4: st.metric("Yenileme", len(orders_df[orders_df['Model'] == 'YENİLEME']))

            st.markdown("### 🎨 Dosyaları Oluştur")

            if not st.session_state.get('files_created', False):
                if st.button("🚀 TÜM DOSYALARI OLUŞTUR", type="primary"):
                    with st.spinner("Dosyalar oluşturuluyor..."):
                        pdf_buffer = create_pdf_labels(orders_df)
                        lazer_pdf = create_lazer_labels(orders_df)
                        uretim_txt = create_uretim_listesi(orders_df)
                        kisisel_txt = create_kisisellestime_listesi(orders_df)
                        store_name = orders_df['Mağaza'].iloc[0] if len(orders_df) > 0 else ''
                        kontrol_pdf = create_kontrol_listesi(orders_df, store_name)

                        st.session_state['pdf_ready'] = pdf_buffer.getvalue()
                        st.session_state['lazer_ready'] = lazer_pdf
                        st.session_state['uretim_ready'] = uretim_txt.encode('utf-8')
                        st.session_state['kisisel_ready'] = kisisel_txt.encode('utf-8')
                        st.session_state['kontrol_ready'] = kontrol_pdf
                        st.session_state['files_created'] = True
                        st.session_state['ts'] = datetime.now().strftime('%Y%m%d_%H%M%S')
                    st.rerun()

            else:
                st.success("✅ Tüm dosyalar hazır!")
                ts = st.session_state.get('ts', 'dosya')
                st.markdown("### 📥 Dosyaları İndir")

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.download_button("📥 PDF Etiketler", data=st.session_state['pdf_ready'],
                        file_name=f"etiketler_{ts}.pdf", mime="application/pdf", key="dl_pdf")
                with c2:
                    if st.session_state.get('lazer_ready'):
                        st.download_button("🟠 Lazer Etiketleri", data=st.session_state['lazer_ready'],
                            file_name=f"lazer_etiketleri_{ts}.pdf", mime="application/pdf", key="dl_lazer")
                    else:
                        st.info("Kişiselleştirme yok")
                with c3:
                    st.download_button("📥 Kontrol Listesi", data=st.session_state['kontrol_ready'],
                        file_name=f"kontrol_{ts}.pdf", mime="application/pdf", key="dl_kontrol")

                c4, c5 = st.columns(2)
                with c4:
                    st.download_button("📥 Üretim Listesi", data=st.session_state['uretim_ready'],
                        file_name=f"uretim_{ts}.txt", mime="text/plain", key="dl_uretim")
                with c5:
                    st.download_button("📥 Kişiselleştirme Listesi", data=st.session_state['kisisel_ready'],
                        file_name=f"kisisellestime_{ts}.txt", mime="text/plain", key="dl_kisisel")

                st.markdown("---")
                if st.button("🔄 Yeni Dosya Yükle", type="secondary"):
                    for k in ['files_created','pdf_ready','lazer_ready','uretim_ready','kisisel_ready','kontrol_ready','ts','last_file_name']:
                        st.session_state.pop(k, None)
                    st.rerun()

        except Exception as e:
            st.error(f"❌ Hata: {str(e)}")
            st.info("💡 CSV için gerekli sütunlar: MagazaAdı, Alıcı, SiparişNumarası, ÜrünAdı, Özellikler")
            st.info("💡 XLSX için: ShipEntegra'dan İndir (Excel) ile alınan dosya olmalı")
else:
    with col1:
        st.info("👆 Lütfen sipariş dosyanızı yükleyin")

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <b>🏭 Sipariş Takip Sistemi Sistemi v1.3</b><br>
    CSV + XLSX → PDF Etiket + Lazer Etiketi + Üretim + Kişiselleştirme + Kontrol PDF
</div>
""", unsafe_allow_html=True)
