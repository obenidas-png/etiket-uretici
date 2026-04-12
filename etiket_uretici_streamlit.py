"""
ETSY ATÖLYE YÖNETİM SİSTEMİ - Streamlit Uygulaması
CSV veya XLSX Yükle → PDF Etiket + 3 TXT Listesi Oluştur
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, HexColor
import re
from zoneinfo import ZoneInfo
import zipfile

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

st.markdown('<h1 class="main-title">🏭 Sipariş Takip Sistemi</h1>', unsafe_allow_html=True)



SHEET_URL = "https://docs.google.com/spreadsheets/d/1xD6d_drnDc9YYnzvT4XGXpuBTtAHB7x2p6Eai1bKlps/edit"
SHEET_COLS = ["Sipariş No", "Müşteri", "Mağaza", "Genişlik", "Model", "Ölçü",
              "Durum", "Not", "Güncelleme Saati", "Ekleyen"]

@st.cache_resource
def get_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(SHEET_URL).sheet1
        return sheet
    except:
        return None

def load_sheet_data():
    sheet = get_gsheet()
    if sheet is None:
        return pd.DataFrame(columns=SHEET_COLS)
    try:
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=SHEET_COLS)
        return pd.DataFrame(data)
    except:
        return pd.DataFrame(columns=SHEET_COLS)

def load_orders_to_session(orders_df):
    """
    Yeni sipariş dosyası yüklenince:
    - Sorunlu (Not dolu) olanlar sheet'te kalır
    - Sorunsuz (Not boş) eski siparişler silinir
    - Yeni siparişler eklenir (sheet'te olmayanlar)
    """
    sheet = get_gsheet()
    if sheet is None:
        return False
    try:
        existing = load_sheet_data()
        istanbul_now = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")

        # Sorunsuz eski siparişleri bul (Not boş olanlar)
        yeni_siparis_nolar = set(str(r["Sipariş No"]) for _, r in orders_df.iterrows())

        if not existing.empty:
            # Mevcut sheet'teki sipariş no + genişlik kombinasyonları
            existing_keys = set(
                str(r.get("Sipariş No","")) + "_" + str(r.get("Genişlik",""))
                for _, r in existing.iterrows()
            )
            # Sadece sheet'te olmayan yeni siparişleri ekle
            new_rows = []
            for _, row in orders_df.iterrows():
                key = str(row["Sipariş No"]) + "_" + str(row.get("Genişlik",""))
                if key not in existing_keys:
                    new_rows.append([
                        str(row["Sipariş No"]), str(row.get("Müşteri","")), str(row.get("Mağaza","")),
                        str(row.get("Genişlik","")), str(row.get("Model","")), str(row.get("Ölçü","")),
                        "", "", "", ""
                    ])
            if new_rows:
                sheet.append_rows(new_rows)
            return len(new_rows)
        else:
            # Sheet boşsa direkt ekle
            sheet.append_row(SHEET_COLS)
            rows = []
            for _, row in orders_df.iterrows():
                rows.append([
                    str(row["Sipariş No"]), str(row.get("Müşteri","")), str(row.get("Mağaza","")),
                    str(row.get("Genişlik","")), str(row.get("Model","")), str(row.get("Ölçü","")),
                    "", "", "", ""
                ])
            if rows:
                sheet.append_rows(rows)
            return len(rows)
    except Exception as e:
        st.error(f"Sheet hatası: {e}")
        return False

def mark_as_problematic(siparis_no, musteri, magaza, genislik, model, olcu, not_text, durum, kullanici):
    """Bir siparişi sorunlu olarak işaretle (notu güncelle)"""
    sheet = get_gsheet()
    if sheet is None:
        return False
    try:
        istanbul_now = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
        # Sipariş sheet'te var mı?
        try:
            cell = sheet.find(str(siparis_no))
            row_num = cell.row
            sheet.update_cell(row_num, 7, durum)
            sheet.update_cell(row_num, 8, not_text)
            sheet.update_cell(row_num, 9, istanbul_now)
            sheet.update_cell(row_num, 10, kullanici)
        except:
            # Yoksa yeni satır ekle (manuel giriş)
            sheet.append_row([
                siparis_no, musteri, magaza, genislik, model, olcu,
                durum, not_text, istanbul_now, kullanici
            ])
        return True
    except:
        return False

def update_order_status(siparis_no, durum, not_text, kullanici):
    sheet = get_gsheet()
    if sheet is None:
        return False
    try:
        istanbul_now = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
        cell = sheet.find(str(siparis_no))
        if cell:
            sheet.update_cell(cell.row, 7, durum)
            sheet.update_cell(cell.row, 8, not_text)
            sheet.update_cell(cell.row, 9, istanbul_now)
            sheet.update_cell(cell.row, 10, kullanici)
        return True
    except:
        return False

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

    value_x = x + 1.7 * cm
    max_value_w = width - 1.7 * cm - 0.1 * cm

    for i, (label, value) in enumerate(rows):
        row_y = y + height - ((i + 0.65) * line_height)
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(text_x, row_y, label)

        val_str = str(value)
        if label == 'Lazer' and val_str:
            # Metni sığdıracak font boyutunu bul
            val_font = font_size - 1
            c.setFont("Helvetica", val_font)
            while val_font > 4 and c.stringWidth(val_str, "Helvetica", val_font) > max_value_w:
                val_font -= 0.5
            c.setFont("Helvetica", val_font)
        else:
            c.setFont("Helvetica", font_size - 1)

        try: c.drawString(value_x, row_y, val_str)
        except: c.drawString(value_x, row_y, turkce_to_ascii(val_str))


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

    col_ratios = [0.11, 0.15, 0.06, 0.06, 0.08, 0.08, 0.28, 0.14, 0.04]
    col_labels = ['Siparis No', 'Musteri Adi', 'Genislik', 'Renk', 'Model', 'Olcu', 'Kisisellestime', 'NOT', 'CHECK']
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
        istanbul_now = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
        c.drawString(margin, y_start + 0.3 * cm, tr("Magaza: " + str(store_name) + "  |  Kontrol Listesi  |  " + istanbul_now))
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
            '',
            '[ ]'
        ]

        # Genişlik, Renk veya Model eksikse kalın yaz
        eksik = (
            not str(row['Genişlik']).strip() or
            not str(row['Renk']).strip() or
            not str(row['Model']).strip() or
            str(row['Genişlik']) == 'nan' or
            str(row['Renk']) == 'nan' or
            str(row['Model']) == 'nan'
        )
        row_font = "Helvetica-Bold" if eksik else "Helvetica"
        x = margin
        for val, w in zip(vals, col_widths):
            max_chars = int(w / (font_size * 0.58))
            c.setFont(row_font, font_size)
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
<style>
/* Tab genel stil */
[data-testid="stTabs"] [role="tablist"] {
    gap: 8px;
}
[data-testid="stTabs"] button[role="tab"] {
    font-size: 1rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    padding: 10px 24px !important;
    border-radius: 8px 8px 0 0 !important;
}
/* Tab 1 - Mavi */
[data-testid="stTabs"] button[role="tab"]:nth-child(1) {
    background-color: #1a3a5c !important;
    color: white !important;
}
[data-testid="stTabs"] button[role="tab"]:nth-child(1):hover {
    background-color: #245080 !important;
}
[data-testid="stTabs"] button[role="tab"]:nth-child(1)[aria-selected="true"] {
    background-color: #2d6aa0 !important;
    color: white !important;
    border-bottom: 3px solid #5ba3d9 !important;
}
/* Tab 2 - Kırmızı */
[data-testid="stTabs"] button[role="tab"]:nth-child(2) {
    background-color: #5c1a1a !important;
    color: white !important;
}
[data-testid="stTabs"] button[role="tab"]:nth-child(2):hover {
    background-color: #7a2222 !important;
}
[data-testid="stTabs"] button[role="tab"]:nth-child(2)[aria-selected="true"] {
    background-color: #a03030 !important;
    color: white !important;
    border-bottom: 3px solid #e07070 !important;
}
</style>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📦 SİPARİŞ YÜKLE & DOSYALAR", "🚨 SORUNLU SİPARİŞ TAKİBİ"])

with tab2:
    st.markdown("### 🚨 Sorunlu Sipariş Takibi")

    col_r, _ = st.columns([1, 5])
    with col_r:
        if st.button("🔄 Yenile", key="refresh_sheet"):
            get_gsheet.clear()

    st.markdown("---")
    # Manuel sipariş ekleme
    with st.expander("➕ Manuel Sipariş No ile Ekle"):
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            m_siparis_no = st.text_input("Sipariş No *", key="m_sipno")
            m_magaza = st.selectbox("Mağaza", ["CPQ", "CRSS", "FRY", "Diğer"], key="m_magaza")
        with col_m2:
            m_durum = st.selectbox("Durum", ["⏳ Bekliyor", "🔄 İşlemde", "✅ Çözüldü"], key="m_durum")
            m_sorun_tipi = st.selectbox("Sorun Kategorisi *",
                ["Yok", "Ölçü Değişikliği", "Genişlik Yok", "Adres-Kargo", "İade-İptal", "Kişiselleştirme", "Diğer"],
                key="m_sorun_tipi")
            m_ek_not = st.text_area("Ek Not (opsiyonel)", key="m_not", height=80)
            m_not = m_sorun_tipi + (" - " + m_ek_not if m_ek_not.strip() else "")
            m_kullanici = st.selectbox("Düzenleyen *", ["SY", "CK", "GD", "HY"], key="m_kullanici")
        if st.button("➕ Ekle", key="m_ekle", type="primary"):
            if not m_siparis_no or not m_kullanici:
                st.warning("Sipariş No ve Düzenleyen zorunlu.")
            else:
                ok = mark_as_problematic(m_siparis_no, "", m_magaza, "", "", "", m_not, m_durum, m_kullanici)
                if ok:
                    st.success(f"#{m_siparis_no} eklendi!")
                    get_gsheet.clear()
                    st.rerun()
                else:
                    st.error("Eklenemedi.")

    st.markdown("---")

    sheet_df = load_sheet_data()

    # Filtre — sadece sorunlular veya tümü
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        goster_filtre = st.selectbox("Göster", ["Sadece Sorunlular", "Tüm Siparişler"], key="goster_filtre")
    with col_f2:
        durum_filtre = st.selectbox("Durum Filtresi", ["Tümü", "⏳ Bekliyor", "🔄 İşlemde", "✅ Çözüldü"], key="durum_filtre")
    with col_f3:
        magaza_listesi = ["Tümü", "CPQ", "CRSS", "FRY"]
        if not sheet_df.empty and "Mağaza" in sheet_df.columns:
            extra = [m for m in sheet_df["Mağaza"].dropna().astype(str).unique().tolist()
                     if m not in magaza_listesi and m.strip() not in ["", "nan"]]
            magaza_listesi += sorted(extra)
        magaza_filtre = st.selectbox("Mağaza", magaza_listesi, key="magaza_filtre")

    if not sheet_df.empty:
        goster_df = sheet_df.copy()
        if goster_filtre == "Sadece Sorunlular":
            not_col = "Not" if "Not" in goster_df.columns else None
            if not_col:
                goster_df = goster_df[~goster_df[not_col].astype(str).str.strip().isin(["", "nan", "Yok"])]
        if durum_filtre != "Tümü":
            goster_df = goster_df[goster_df["Durum"] == durum_filtre]
        if magaza_filtre != "Tümü" and "Mağaza" in goster_df.columns:
            goster_df = goster_df[goster_df["Mağaza"].astype(str) == magaza_filtre]
        # Güncelleme tarihine göre sırala (en eski üste, tarihi olmayanlar sona)
        def parse_tarih(t):
            try:
                return pd.to_datetime(str(t), format="%d.%m.%Y %H:%M")
            except:
                return pd.Timestamp.max
        goster_df = goster_df.copy()
        tarih_col = "Güncelleme Saati" if "Güncelleme Saati" in goster_df.columns else (
                    "Tamamlanma Saati" if "Tamamlanma Saati" in goster_df.columns else None)
        if tarih_col:
            goster_df["_sort"] = goster_df[tarih_col].apply(parse_tarih)
            goster_df = goster_df.sort_values("_sort", ascending=True).drop(columns=["_sort"])
        st.markdown(f"**{len(goster_df)} kayıt**")
    else:
        goster_df = pd.DataFrame(columns=SHEET_COLS)
        st.info("Henüz sipariş yüklenmemiş.")

    # Mevcut siparişleri listele
    for idx, row in goster_df.iterrows():
        siparis_no = str(row.get("Sipariş No", ""))
        musteri = str(row.get("Müşteri", ""))
        durum = str(row.get("Durum", ""))
        not_text = str(row.get("Not", ""))
        ekleyen = str(row.get("Ekleyen", ""))
        guncelleme = str(row.get("Güncelleme Saati", ""))
        genislik = str(row.get("Genişlik", ""))
        model = str(row.get("Model", ""))
        olcu = str(row.get("Ölçü", ""))

        has_problem = not_text.strip() not in ["", "nan"]
        icon = "🚨" if has_problem else "📦"
        durum_icon = "✅" if durum == "✅ Çözüldü" else ("🔄" if durum == "🔄 İşlemde" else ("⏳" if durum == "⏳ Bekliyor" else ""))

        # Sorun notunun özeti etikette görünsün
        not_ozet = ""
        if has_problem and not_text.strip() not in ["", "nan"]:
            not_ozet = " — " + not_text[:50] + ("..." if len(not_text) > 50 else "")

        label = f"{icon} #{siparis_no} [{row.get('Mağaza','')}] — {musteri} | {genislik} {model} {olcu}"
        if has_problem:
            label += f" | {durum_icon} {durum}{not_ozet}"

        with st.expander(label):
            if has_problem and (ekleyen.strip() not in ["","nan"] or guncelleme.strip() not in ["","nan"]):
                st.caption(f"Son düzenleyen: {ekleyen} | {guncelleme}")

            col_a, col_b = st.columns([2, 1])
            with col_a:
                # Mevcut notu kategori + ek not olarak ayır
                mevcut_kategori = ""
                mevcut_aciklama = not_text if not_text not in ["", "nan"] else ""
                for _tip in ["Yok", "Ölçü Değişikliği", "Genişlik Yok", "Adres-Kargo", "İade-İptal", "Kişiselleştirme", "Diğer"]:
                    if mevcut_aciklama.startswith(_tip):
                        mevcut_kategori = _tip
                        mevcut_aciklama = mevcut_aciklama[len(_tip):].lstrip(" |-").strip()
                        break
                sorun_tipi = st.selectbox(
                    "Sorun Kategorisi",
                    ["Yok", "Ölçü Değişikliği", "Genişlik Yok", "Adres-Kargo", "İade-İptal", "Kişiselleştirme", "Diğer"],
                    index=["Ölçü Değişikliği","Genişlik Yok","Adres-Kargo","İade-İptal","Kişiselleştirme","Diğer"].index(mevcut_kategori)
                    if mevcut_kategori in ["Ölçü Değişikliği","Genişlik Yok","Adres-Kargo","İade-İptal","Kişiselleştirme","Diğer"] else 0,
                    key=f"tip_{siparis_no}_{idx}"
                )
                ek_not = st.text_area("Ek Not (opsiyonel)", value=mevcut_aciklama,
                    placeholder="Ek açıklama...", key=f"not_{siparis_no}_{idx}", height=80)
                yeni_not = sorun_tipi + (" - " + ek_not if ek_not.strip() else "")
            with col_b:
                yeni_durum = st.selectbox("Durum", ["⏳ Bekliyor", "🔄 İşlemde", "✅ Çözüldü"],
                    index=["⏳ Bekliyor","🔄 İşlemde","✅ Çözüldü"].index(durum)
                    if durum in ["⏳ Bekliyor","🔄 İşlemde","✅ Çözüldü"] else 0,
                    key=f"durum_{siparis_no}_{idx}")
                duzenleyen = st.selectbox("Düzenleyen", ["SY", "CK", "GD", "HY"], key=f"kul_{siparis_no}_{idx}")
                if st.button("💾 Kaydet", key=f"save_{siparis_no}_{idx}", type="primary"):
                    if not yeni_not.strip():
                        st.warning("Sorun notu gerekli.")
                    else:
                        ok = mark_as_problematic(
                            siparis_no, musteri, str(row.get("Mağaza","")),
                            genislik, model, olcu, yeni_not, yeni_durum, duzenleyen
                        )
                        if ok:
                            st.success("Kaydedildi!")
                            get_gsheet.clear()
                            st.rerun()
                        else:
                            st.error("Kayıt başarısız.")



with tab1:
    col_main, col_info = st.columns([3, 1])

with col_info:
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

with col_main:
    st.markdown("### 📂 Sipariş Dosyası Yükle")
    uploaded_file = st.file_uploader(
        "📦 Dosyayı buraya sürükleyin veya tıklayın",
        type=['csv', 'xlsx', 'xlsm'],
        help="ShipEntegra: Siparişler > İndir (Excel) seçilerek indirilen dosyayı yükleyin"
    )

if uploaded_file:
    with col_main:
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

            with st.spinner("Sipariş listesi güncelleniyor..."):
                sonuc = load_orders_to_session(orders_df)
                if sonuc is False:
                    st.warning("⚠️ Google Sheets bağlantısı kurulamadı.")
                else:
                    st.success(f"✅ {sonuc} yeni sipariş takip listesine eklendi, sorunlular korundu.")



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

                has_lazer = bool(st.session_state.get('lazer_ready'))
                num_cols = 5 if has_lazer else 4
                cols = st.columns(num_cols)

                # ZIP butonu
                istanbul_now = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d%m%Y_%H%M")
                store_name_zip = orders_df['Mağaza'].iloc[0] if len(orders_df) > 0 else 'siparis'
                zip_filename = f"{store_name_zip}_{istanbul_now}.zip"

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(f"kargo_etiketleri_{ts}.pdf", st.session_state['pdf_ready'])
                    if st.session_state.get('lazer_ready'):
                        zf.writestr(f"lazer_etiketleri_{ts}.pdf", st.session_state['lazer_ready'])
                    zf.writestr(f"fsm_uretim_{ts}.txt", st.session_state['uretim_ready'])
                    zf.writestr(f"kisisellestime_{ts}.txt", st.session_state['kisisel_ready'])
                    zf.writestr(f"kontrol_{ts}.pdf", st.session_state['kontrol_ready'])
                zip_buffer.seek(0)

                st.markdown("""
<style>
div[data-testid="stDownloadButton"]:first-of-type button {
    font-size: 1.2rem !important;
}
</style>
""", unsafe_allow_html=True)
                st.download_button(
                    "📦  TÜM DOSYALARI İNDİR (.zip)",
                    data=zip_buffer.getvalue(),
                    file_name=zip_filename,
                    mime="application/zip",
                    key="dl_zip",
                    type="primary",
                    use_container_width=True
                )
                st.markdown("---")

                btn_style = """
<style>
[data-testid="stDownloadButton"] button {
    font-size: 1.35rem !important;
    padding: 14px 10px !important;
    height: auto !important;
}
[data-testid="stDownloadButton"] button svg,
[data-testid="stDownloadButton"] button span:first-child {
    font-size: 1.6rem !important;
}
</style>
"""
                st.markdown(btn_style, unsafe_allow_html=True)

                with cols[0]:
                    st.download_button("📦  Kargo Etiketleri", data=st.session_state['pdf_ready'],
                        file_name=f"kargo_etiketleri_{ts}.pdf", mime="application/pdf", key="dl_pdf")
                if has_lazer:
                    with cols[1]:
                        st.download_button("🟠  Lazer Etiketleri", data=st.session_state['lazer_ready'],
                            file_name=f"lazer_etiketleri_{ts}.pdf", mime="application/pdf", key="dl_lazer")

                with cols[-3]:
                    st.download_button("📝  FSM Üretim Listesi", data=st.session_state['uretim_ready'],
                        file_name=f"fsm_uretim_{ts}.txt", mime="text/plain", key="dl_uretim")
                with cols[-2]:
                    st.download_button("✍️  Kişiselleştirme Listesi", data=st.session_state['kisisel_ready'],
                        file_name=f"kisisellestime_{ts}.txt", mime="text/plain", key="dl_kisisel")
                with cols[-1]:
                    st.download_button("📋  Kontrol Listesi", data=st.session_state['kontrol_ready'],
                        file_name=f"kontrol_{ts}.pdf", mime="application/pdf", key="dl_kontrol")

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
    with col_main:
        st.info("👆 Lütfen sipariş dosyanızı yükleyin")

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <b>🏭 Sipariş Takip Sistemi v1.3</b><br>
    CSV + XLSX → PDF Etiket + Lazer Etiketi + Üretim + Kişiselleştirme + Kontrol PDF
</div>
""", unsafe_allow_html=True)
