"""
ETSY ATÖLYE YÖNETİM SİSTEMİ - Streamlit Uygulaması
CSV veya XLSX Yükle → PDF Etiket + 3 TXT Listesi Oluştur
CHEPNIQ, FORY, CRSS mağazaları API'den otomatik çekilir.
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import urllib.request
import urllib.parse
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, HexColor
import re
from zoneinfo import ZoneInfo
import zipfile
import requests

st.set_page_config(page_title="Sipariş Takip Sistemi", page_icon="🏭", layout="wide")

st.markdown("""
<style>
    .main-title {
        text-align: center; padding: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px; color: white; margin-bottom: 30px;
    }
    .stButton>button { width: 100%; background-color: #667eea; color: white; font-weight: bold; }
    [data-testid="stFileUploader"] {
        background-color: #fff4e6;
        border: 2px dashed #ff8c00;
        border-radius: 12px;
        padding: 20px;
    }
    .api-box {
        background-color: #eef4ff;
        border: 1.5px solid #667eea;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-title">🏭 Sipariş Takip Sistemi</h1>', unsafe_allow_html=True)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1xD6d_drnDc9YYnzvT4XGXpuBTtAHB7x2p6Eai1bKlps/edit"
SHEET_COLS = ["Sipariş No", "Müşteri", "Mağaza", "Genişlik", "Model", "Ölçü",
              "Durum", "Not", "Güncelleme Saati", "Ekleyen"]

SHIPENTEGRA_API_BASE = "https://api.shipentegra.com/v1"

# ─── Mağaza API bilgileri ───────────────────────────────
STORE_CONFIGS = {
    "CPQ": {
        "label": "Chepniq",
        "api_key_secret": "shipentegra",   # secrets.toml key adı
        "color": "#1a3a5c",
    },
    "FRY": {
        "label": "Foria",
        "api_key_secret": "shipentegra_fory",
        "color": "#5c1a1a",
    },
    "CRSS": {
        "label": "Cerasus",
        "api_key_secret": "shipentegra_crss",
        "color": "#1a5c2a",
    },
}

# ─── API yardımcı fonksiyonlar ──────────────────────────

def get_store_credentials(store_code):
    cfg = STORE_CONFIGS.get(store_code, {})
    secret_key = cfg.get("api_key_secret", "")
    try:
        key = st.secrets[secret_key]["api_key"]
        secret = st.secrets[secret_key]["api_secret"]
        return key, secret
    except Exception:
        return None, None


def get_bearer_token(client_id, client_secret):
    try:
        resp = requests.post(
            f"{SHIPENTEGRA_API_BASE}/auth/token",
            json={"clientId": client_id, "clientSecret": client_secret},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()["data"]["accessToken"]
        return None
    except Exception:
        return None


def is_valid_order(o):
    order_id = str(o.get("order_id", ""))
    if order_id.startswith("M"):
        try:
            order_date_str = o.get("orderDate", "")
            if order_date_str:
                order_date = datetime.datetime.strptime(str(order_date_str), "%Y-%m-%d %H:%M:%S")
                return (datetime.datetime.now() - order_date).days <= 5
        except:
            pass
        return False  # tarih parse edilemezse ekleme
    return True


def fetch_pending_orders_for_store(store_code):
    client_id, client_secret = get_store_credentials(store_code)
    if not client_id:
        # Fallback: hardcoded keys
        hardcoded = {
            "CPQ":  (None, None),
            "FRY":  ("e62b15fc78f1a19dbe464b17b8e84b76", "499ecf825a609b96c011b22bde71e4e807970bd9"),
            "CRSS": ("6eea9df8ed8f5ce281d984d735187629", "068ba54f90c07885bb69348e870e5579972e0512"),
        }
        client_id, client_secret = hardcoded.get(store_code, (None, None))

    if not client_id:
        st.error(f"{store_code} için API anahtarı bulunamadı.")
        return None

    token = get_bearer_token(client_id, client_secret)
    if not token:
        st.error(f"{store_code} token alınamadı. Kimlik bilgilerini kontrol edin.")
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    all_pending = []
    page = 1

    try:
        while True:
            resp = requests.get(
                f"{SHIPENTEGRA_API_BASE}/orders",
                headers=headers,
                params={"page": page, "limit": 100},
                timeout=30,
            )
            if resp.status_code == 401:
                st.error(f"{store_code}: Token geçersiz (401).")
                return None
            if resp.status_code != 200:
                st.error(f"{store_code} API hatası: {resp.status_code}")
                return None

            data = resp.json()
            orders = data.get("data", {}).get("orders", [])
            if not orders:
                break

            pending = [o for o in orders if (str(o.get("status", "")) == "2" or str(o.get("my_status", "")) == "2") and is_valid_order(o)]
            for o in orders:
                if str(o.get('order_id','')) == '4043438286':
                    st.write(f"FOUND - my_note: {repr(o.get('my_note'))} | my_status: {repr(o.get('my_status'))} | status: {repr(o.get('status'))} | tags: {repr(o.get('tags'))}")
            all_pending.extend(pending)

            if len(orders) < 100:
                break
            page += 1

    except requests.exceptions.Timeout:
        st.error(f"{store_code}: API isteği zaman aşımına uğradı.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"{store_code} bağlantı hatası: {e}")
        return None

    if not all_pending:
        st.warning(f"{store_code}: Bekleyen sipariş bulunamadı.")
        return pd.DataFrame()

    df = api_orders_to_df(all_pending, store_code)
    return df


def api_orders_to_df(orders, store_code="CPQ"):
    label_map = {"CPQ": "Chepniq", "FRY": "Foria", "CRSS": "Cerasus"}
    store_label = label_map.get(store_code, store_code)
    rows = []
    for o in orders:
        order_no = str(o.get("order_id") or o.get("marketplaceOrderId") or o.get("orderId") or "")
        buyer    = str(o.get("ship_to_name") or "")
        product  = str(o.get("name") or o.get("title") or "")
        gift_msg = str(o.get("gift_message") or "")
        qty      = int(o.get("count") or o.get("quantity") or 1)

        variations_raw = o.get("variations") or []

        # Her variation grubunu ayrı satır olarak topla
        var_groups = []
        for var_group in variations_raw:
            if isinstance(var_group, list):
                opts = {}
                for v in var_group:
                    if isinstance(v, dict) and v.get("name") and v.get("value") is not None:
                        opts[v["name"]] = str(v["value"])
                if opts:
                    var_groups.append(opts)

        # Eğer variation grubu sayısı qty ile eşleşiyorsa her grubu ayrı satır yap
        if len(var_groups) >= qty > 1:
            for i in range(qty):
                opts = var_groups[i] if i < len(var_groups) else var_groups[-1]
                ozellikler_parts = [f"Ad:{k},Değer:{v}" for k, v in opts.items()]
                rows.append({
                    "MagazaAdı":       store_label,
                    "SiparişNumarası": order_no,
                    "Alıcı":           buyer,
                    "ÜrünAdı":         product,
                    "Özellikler":      ",".join(ozellikler_parts) if ozellikler_parts else None,
                    "_BuyerNote":      str(o.get("customer_note") or ""),
                    "_GiftMessage":    gift_msg,
                    "_ShipBy":         str(o.get("ship_by_date") or ""),
                    "_OrderTotal":     o.get("total_price") or 0,
                })
        else:
            # Tüm variation gruplarını birleştir (tek satır)
            opts = {}
            for vg in var_groups:
                for k, v in vg.items():
                    if k not in opts:
                        opts[k] = v
            ozellikler_parts = [f"Ad:{k},Değer:{v}" for k, v in opts.items()]
            rows.append({
                "MagazaAdı":       store_label,
                "SiparişNumarası": order_no,
                "Alıcı":           buyer,
                "ÜrünAdı":         product,
                "Özellikler":      ",".join(ozellikler_parts) if ozellikler_parts else None,
                "_BuyerNote":      str(o.get("customer_note") or ""),
                "_GiftMessage":    gift_msg,
                "_ShipBy":         str(o.get("ship_by_date") or ""),
                "_OrderTotal":     o.get("total_price") or 0,
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ─── Google Sheets ──────────────────────────────────────

def telegram_bildir(mesaj):
    try:
        token = st.secrets["telegram"]["token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = f"chat_id={chat_id}&text={urllib.parse.quote(mesaj)}&parse_mode=HTML"
        req = urllib.request.Request(url, data=data.encode(), method="POST")
        urllib.request.urlopen(req, timeout=5)
    except:
        pass


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
    sheet = get_gsheet()
    if sheet is None:
        return False
    try:
        existing = load_sheet_data()
        if not existing.empty:
            existing_keys = set(
                str(r.get("Sipariş No","")) + "_" + str(r.get("Genişlik","")) + "_" + str(r.get("Ölçü",""))
                for _, r in existing.iterrows()
            )
            new_rows = []
            for _, row in orders_df.iterrows():
                key = str(row["Sipariş No"]) + "_" + str(row.get("Genişlik","")) + "_" + str(row.get("Ölçü",""))
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
    sheet = get_gsheet()
    if sheet is None:
        return False
    try:
        istanbul_now = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
        try:
            cell = sheet.find(str(siparis_no))
            row_num = cell.row
            sheet.update_cell(row_num, 7, durum)
            sheet.update_cell(row_num, 8, not_text)
            sheet.update_cell(row_num, 9, istanbul_now)
            sheet.update_cell(row_num, 10, kullanici)
        except:
            sheet.append_row([
                siparis_no, musteri, magaza, genislik, model, olcu,
                durum, not_text, istanbul_now, kullanici
            ])
        telegram_bildir(
            f"🚨 <b>Sorunlu Sipariş</b>\n"
            f"📦 #{siparis_no} [{magaza}]\n"
            f"👤 {musteri}\n"
            f"⚠️ {not_text}\n"
            f"📊 {durum}\n"
            f"✏️ {kullanici} · {istanbul_now}"
        )
        return True
    except:
        return False


# ─── Dosya yükleme / parse ──────────────────────────────

def xlsx_to_standard_df(df_xlsx):
    rows = []
    for _, row in df_xlsx.iterrows():
        ozellikler_parts = []
        for i in range(1, 4):
            name = row.get(f'Options Name {i}')
            value = row.get(f'Options Value {i}')
            if pd.notna(name) and pd.notna(value):
                ozellikler_parts.append(f"Ad:{name},Değer:{value}")
        ozellikler = ",".join(ozellikler_parts)
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


def clean_crss_product(product):
    """Cerasus ürün adından gereksiz metal/altın ifadelerini temizler."""
    remove = [
        '14k solid gold', '14k gold', 'solid gold', '14k white gold', '14k yellow gold',
        '14k rose gold', 'sterling silver', 'gold vermeil', 'white gold vermeil',
        'yellow gold vermeil', 'rose gold vermeil', '14k', 'solid', 'dainty', 'minimalist',
        'personalized', 'real gold', 'genuine', 'handmade', 'custom',
    ]
    result = product.lower()
    for r in remove:
        result = result.replace(r, ' ')
    # Birden fazla boşlukları temizle
    import re
    result = re.sub(r'\s+', ' ', result).strip()
    # İlk harfleri büyüt
    result = result.title()
    # 25 karakter sınırı
    if len(result) > 25:
        result = result[:22] + '...'
    return result


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
            properties_str = str(row['Özellikler'])
            pattern = r'Ad:([^,]+),Değer:([^,]+(?:,[^A][^d][^:]*)*?)(?=,Ad:|$)'
            matches = re.findall(pattern, properties_str)
            for key, value in matches:
                value_clean = value.replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
                props[key.strip()] = value_clean.strip()

        if row.get('_BuyerNote'):
            props.setdefault('Personalization', row['_BuyerNote'])

        if 'cerasus' in store_name.lower():
            product_clean = clean_crss_product(product.split(' - ')[0])

            # Renk: Color > General material > Band color > ürün adından
            color = (props.get('Color') or props.get('General material') or
                     props.get('Band color') or props.get('Metal') or '')
            if not color:
                if '14k yellow gold' in product_lower or 'yellow gold' in product_lower: color = '14K Yellow Gold'
                elif '14k white gold' in product_lower or 'white gold' in product_lower: color = '14K White Gold'
                elif '14k rose gold' in product_lower or 'rose gold' in product_lower: color = '14K Rose Gold'
                elif 'sterling silver' in product_lower or 'silver' in product_lower: color = 'Sterling Silver'

            # Ölçü: Ring size > Necklace Lenght > Necklace Length
            olcu = (props.get('Ring size') or props.get('Necklace Lenght') or
                    props.get('Necklace Length') or props.get('Chain Length') or '')

            orders.append({'Mağaza': store_code, 'Sipariş No': row.get('SiparişNumarası', ''),
                'Müşteri': row.get('Alıcı', ''), 'Genişlik': '', 'Renk': color, 'Model': product_clean,
                'Ölçü': olcu, 'Kişiselleştirme': props.get('Personalization', ''),
                'Özel Not': '', 'Ürün': product_clean})
        else:
            model = ''
            color = ''
            width = props.get('Width', props.get('Band Width', ''))
            if 'white gold' in product_lower or 'beyaz' in product_lower: color = 'BEYAZ'
            elif 'yellow gold' in product_lower or 'sarı' in product_lower or 'gold filled' in product_lower: color = 'SARI'
            elif 'rose' in product_lower or 'pembe' in product_lower: color = 'ROSE'
            if 'matte' in product_lower or 'mat' in product_lower:
                if color == 'BEYAZ': color = 'MAT BEYAZ'

            if 'resizing' in product_lower or 'size adjustment' in product_lower or 'replacement' in product_lower: model = 'YENİLEME'
            elif 'bevel' in product_lower: model = 'ÇATI MAT' if ('matte' in product_lower or 'mat' in product_lower) else 'ÇATI'
            elif 'dome' in product_lower: model = 'BOMBE'
            elif 'flat' in product_lower: model = 'DÜZ'
            elif 'oval' in product_lower or 'solitaire' in product_lower: model = 'TEKTAŞ'
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
                if size1:
                    orders.append({'Mağaza': store_code, 'Sipariş No': row.get('SiparişNumarası', ''),
                        'Müşteri': row.get('Alıcı', ''), 'Genişlik': width1, 'Renk': color, 'Model': model,
                        'Ölçü': size1, 'Kişiselleştirme': props.get('Personalization', ''),
                        'Özel Not': str(row.get('_MyNote', '') or ''), 'Ürün': product})
                if size2:
                    orders.append({'Mağaza': store_code, 'Sipariş No': row.get('SiparişNumarası', ''),
                        'Müşteri': row.get('Alıcı', ''), 'Genişlik': width2, 'Renk': color, 'Model': model,
                        'Ölçü': size2, 'Kişiselleştirme': props.get('Personalization', ''),
                        'Özel Not': str(row.get('_MyNote', '') or ''), 'Ürün': product})
            else:
                orders.append({'Mağaza': store_code, 'Sipariş No': row.get('SiparişNumarası', ''),
                    'Müşteri': row.get('Alıcı', ''), 'Genişlik': width.upper() if width else '',
                    'Renk': color, 'Model': model.upper() if model else '', 'Ölçü': ring_size,
                    'Kişiselleştirme': props.get('Personalization', ''),
                    'Özel Not': str(row.get('_MyNote', '') or ''), 'Ürün': product})

    siparis_sayilari = pd.Series([o['Sipariş No'] for o in orders])
    tekrar_edenler = set(siparis_sayilari[siparis_sayilari.duplicated(keep=False)].tolist())
    for o in orders:
        o['Çoklu'] = o['Sipariş No'] in tekrar_edenler

    return pd.DataFrame(orders)


# ─── Yardımcı fonksiyonlar ──────────────────────────────

def turkce_to_ascii(text):
    if not text or pd.isna(text): return ''
    text = str(text)
    for a, b in {'ı':'i','İ':'I','ş':'s','Ş':'S','ğ':'g','Ğ':'G','ü':'u','Ü':'U','ö':'o','Ö':'O','ç':'c','Ç':'C'}.items():
        text = text.replace(a, b)
    return text


def convert_size_to_decimal(size_str):
    if not size_str or pd.isna(size_str): return '0.00'
    size_str = str(size_str).strip().replace(' US', '').replace('US', '').strip()
    if '/' in size_str:
        parts = size_str.split()
        if len(parts) == 2:
            whole = int(parts[0])
            num, den = parts[1].split('/')
            decimal = whole + int(num)/int(den)
        elif len(parts) == 1:
            num, den = parts[0].split('/')
            decimal = int(num)/int(den)
        else:
            decimal = float(size_str.split()[0])
    else:
        try: decimal = float(size_str)
        except: return '0.00'
    return f"{decimal:.2f}"


def get_model_priority(model):
    model_lower = str(model).lower()
    if 'bombe' in model_lower: return 1
    elif 'çati' in model_lower or 'cati' in model_lower: return 2
    elif 'düz' in model_lower or 'duz' in model_lower or 'flat' in model_lower: return 3
    elif 'oval' in model_lower or 'tektaş' in model_lower or 'tektas' in model_lower: return 4
    else: return 5


def get_width_numeric(width_str):
    if not width_str or pd.isna(width_str): return 0
    width_str = str(width_str).upper().replace('MM', '').strip()
    try: return int(width_str)
    except: return 0


# ─── PDF / çıktı fonksiyonlar ───────────────────────────

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

    if 'cerasus' in store or store == 'crss':
        line_height = height / 7
        for i in range(1, 7):
            c.setLineWidth(0.3)
            c.line(x, y + (i * line_height), x + width, y + (i * line_height))
        note = ''
        if pd.notna(data.get('Kişiselleştirme')):
            note = str(data['Kişiselleştirme']).replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
            note = turkce_to_ascii(note[:30])
        coklu_label = ' (COKLU SIPARIS)' if coklu else ''
        olcu_crss = str(data.get('Ölçü', ''))
        rows = [
            ('Magaza', 'CRSS' + coklu_label),
            ('Siparis No', str(data['Sipariş No'])),
            ('Musteri', turkce_to_ascii(str(data['Müşteri'])[:20])),
            ('Urun', turkce_to_ascii(str(data['Ürün'])[:25])),
            ('Olcu/Zincir', olcu_crss),
            ('Renk', turkce_to_ascii(str(data['Renk'])[:15])),
            ('Not', note)
        ]
    else:
        line_height = height / 8
        for i in range(1, 8):
            c.setLineWidth(0.3)
            c.line(x, y + (i * line_height), x + width, y + (i * line_height))

        pers_text_line1 = ''
        pers_text_line2 = ''
        if pd.notna(data['Kişiselleştirme']):
            pers_full = str(data['Kişiselleştirme']).replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
            if len(pers_full) <= 30:
                pers_text_line1 = pers_full
            else:
                cut_point = pers_full[:30].rfind(' ') if ' ' in pers_full[:30] else 30
                pers_text_line1 = pers_full[:cut_point]
                pers_text_line2 = pers_full[cut_point:60].strip()

        color = str(data.get('Renk', ''))
        color_lower = color.lower()
        if 'yellow' in color_lower or 'sari' in color_lower or 'sarı' in color_lower: color_short = 'SARI'
        elif 'rose' in color_lower or 'pembe' in color_lower: color_short = 'ROSE'
        elif 'white' in color_lower or 'beyaz' in color_lower:
            color_short = 'MAT BEYAZ' if ('matte' in color_lower or 'mat' in color_lower) else 'BEYAZ'
        else:
            color_short = turkce_to_ascii(color[:10])

        ozel_not = str(data.get('Özel Not', '')) if pd.notna(data.get('Özel Not', '')) else ''
        coklu_label = ' (COKLU SIPARIS)' if coklu else ''
        rows = [
            ('Magaza', str(data.get('Mağaza', 'CPQ')) + coklu_label),
            ('Siparis No', str(data['Sipariş No'])),
            ('Musteri Adi', turkce_to_ascii(str(data['Müşteri'])[:25])),
            ('Genislik', str(data['Genişlik'])),
            ('Renk', color_short),
            ('Model', turkce_to_ascii(str(data['Model']))),
            ('Olcu', str(data['Ölçü'])),
            ('Lazer', pers_text_line1),
        ]
        if pers_text_line2:
            rows.append(('', pers_text_line2))
        if ozel_not:
            rows.append(('Not', turkce_to_ascii(ozel_not[:30])))

    value_x = x + 1.7 * cm
    max_value_w = width - 1.7 * cm - 0.1 * cm

    for i, (label, value) in enumerate(rows):
        row_y = y + height - ((i + 0.65) * line_height)
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(text_x, row_y, label)
        val_str = str(value)
        if (label == 'Lazer' or label == '') and val_str:
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
    label_width, label_height = 9.5 * cm, 5.0 * cm   # biraz daha uzun (ölçü için)
    margin_x, margin_y = 0.5 * cm, 0.5 * cm
    gap_x, gap_y = 0.3 * cm, 0.3 * cm
    labels_per_row, labels_per_column = 2, 5
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
    c.setStrokeColor(HexColor('#ff8c00'))
    c.setLineWidth(1.5)
    c.rect(x, y, width, height)

    font_size = 8
    label_col_w = 2.0 * cm
    text_x = x + 0.2 * cm

    pers = str(data.get('Kişiselleştirme', ''))
    pers = pers.replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
    pers_ascii = turkce_to_ascii(pers)

    c.setFillColor(HexColor('#cc6600'))
    c.setFont("Helvetica-Bold", font_size + 1)
    c.drawString(text_x, y + height - 0.5 * cm, "LAZER ETIKETI")
    c.setFillColor(black)

    c.setStrokeColor(HexColor('#ff8c00'))
    c.setLineWidth(0.8)
    c.line(x, y + height - 0.7 * cm, x + width, y + height - 0.7 * cm)

    row_y = y + height - 1.1 * cm

    # Müşteri
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Musteri:")
    c.setFont("Helvetica", font_size)
    c.drawString(text_x + label_col_w, row_y, turkce_to_ascii(str(data.get('Müşteri', ''))[:35]))

    # Genişlik
    row_y -= 0.55 * cm
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Genislik:")
    c.setFont("Helvetica", font_size)
    c.drawString(text_x + label_col_w, row_y, str(data.get('Genişlik', '')))

    # Renk
    row_y -= 0.55 * cm
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Renk:")
    c.setFont("Helvetica", font_size)
    color = str(data.get('Renk', ''))
    color_lower = color.lower()
    if 'yellow' in color_lower or 'sari' in color_lower or 'sarı' in color_lower: color_short = 'SARI'
    elif 'rose' in color_lower or 'pembe' in color_lower: color_short = 'ROSE'
    elif 'white' in color_lower or 'beyaz' in color_lower:
        color_short = 'MAT BEYAZ' if ('matte' in color_lower or 'mat' in color_lower) else 'BEYAZ'
    else:
        color_short = turkce_to_ascii(color[:10])
    c.drawString(text_x + label_col_w, row_y, color_short)

    # Ölçü — YENİ
    row_y -= 0.55 * cm
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Olcu:")
    c.setFont("Helvetica", font_size)
    c.drawString(text_x + label_col_w, row_y, str(data.get('Ölçü', '')))

    # Lazer yazısı
    row_y -= 0.55 * cm
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Lazer:")

    chars_per_line = int((width - label_col_w - 0.4 * cm) / (font_size * 0.52))
    c.setFont("Helvetica", font_size)
    line_start = 0
    for line_i in range(4):
        chunk = pers_ascii[line_start:line_start + chars_per_line]
        if not chunk:
            break
        lx = text_x + label_col_w if line_i == 0 else text_x + 0.3 * cm
        c.drawString(lx, row_y - (line_i * 0.52 * cm), chunk)
        line_start += chars_per_line


def create_uretim_listesi(orders_df):
    production = orders_df[orders_df['Model'] != 'YENİLEME'].copy()
    if len(production) == 0:
        return "Üretim gerektiren sipariş yok."
    production['Ölçü_Ondalık'] = production['Ölçü'].apply(convert_size_to_decimal)
    production['Ölçü_Sayısal'] = production['Ölçü_Ondalık'].apply(lambda x: float(x) if x else 0.0)
    production['Model_Öncelik'] = production['Model'].apply(get_model_priority)
    production['Genişlik_Sayısal'] = production['Genişlik'].apply(get_width_numeric)
    production_sorted = production.sort_values(by=['Model_Öncelik', 'Genişlik_Sayısal', 'Ölçü_Sayısal'])
    output = "Üretim Listesi\n==============\n\n"
    output += f"{'Genişlik':<10}{'Model':<15}{'Ölçü (Ondalık)':<20}Müşteri\n"
    output += f"{'-'*9} {'-'*14} {'-'*19} {'-'*24}\n"
    for _, row in production_sorted.iterrows():
        musteri = str(row['Müşteri']) if str(row.get('Müşteri','')) not in ['', 'nan', 'None'] else ''
        output += f"{str(row['Genişlik']):<10}{str(row['Model']):<15}{str(row['Ölçü_Ondalık']):<20}{musteri}\n"
    yenileme = orders_df[orders_df['Model'] == 'YENİLEME'].copy()
    for _, row in yenileme.iterrows():
        musteri = str(row.get('Müşteri','')) if str(row.get('Müşteri','')) not in ['','nan','None'] else ''
        olcu = str(row.get('Ölçü',''))
        output += f"{'':<10}{'':<15}{olcu:<20}{musteri} YENİLEME\n"

    output += "\n\n"
    output += "Üretim Listesi (Kopyalama için - İsimsiz)\n"
    output += "==========================================\n\n"
    output += f"{'Genişlik':<10}{'Model':<15}{'Ölçü (Ondalık)':<20}\n"
    output += f"{'-'*9} {'-'*14} {'-'*19}\n"
    for _, row in production_sorted.iterrows():
        output += f"{str(row['Genişlik']):<10}{str(row['Model']):<15}{str(row['Ölçü_Ondalık']):<20}\n"
    for _, row in yenileme.iterrows():
        olcu = str(row.get('Ölçü',''))
        output += f"{'':<10}{'':<15}{olcu:<20}YENİLEME\n"
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
        output += f"Müşteri: {row['Müşteri']}\nGenişlik: {row['Genişlik']}\nÖlçü: {row['Ölçü']}\nKişiselleştirme:\n   {text}\n" + "-" * 80 + "\n\n"
    return output


def create_kontrol_listesi(orders_df, store_name=''):
    def tr(text):
        if not text or str(text) == 'nan': return ''
        text = str(text)
        for a, b in {'ı':'i','İ':'I','ş':'s','Ş':'S','ğ':'g','Ğ':'G','ü':'u','Ü':'U','ö':'o','Ö':'O','ç':'c','Ç':'C'}.items():
            text = text.replace(a, b)
        return text

    buffer = io.BytesIO()
    page_w, page_h = A4
    margin = 1 * cm
    usable_w = page_w - 2 * margin

    col_ratios = [0.16, 0.18, 0.08, 0.08, 0.10, 0.10, 0.24, 0.06]
    col_labels = ['Siparis No', 'Musteri Adi', 'Genislik', 'Renk', 'Model', 'Olcu', 'Kisisellestime', 'CHECK']
    col_widths = [usable_w * r for r in col_ratios]

    n = len(orders_df)
    if n <= 15:   font_size, row_h = 8, 1.0 * cm
    elif n <= 25: font_size, row_h = 7, 0.85 * cm
    elif n <= 40: font_size, row_h = 6, 0.72 * cm
    else:         font_size, row_h = 5.5, 0.65 * cm

    header_h = row_h * 1.3
    c = canvas.Canvas(buffer, pagesize=A4)

    def draw_header(y_start):
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", font_size + 1)
        istanbul_now = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
        c.drawString(margin, y_start + 0.3 * cm, tr(f"Magaza: {store_name}  |  Kontrol Listesi  |  {istanbul_now}"))
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
        if pd.notna(row.get('Kişiselleştirme', '')):
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

        eksik = (
            not str(row['Genişlik']).strip() or not str(row['Renk']).strip() or
            not str(row['Model']).strip() or str(row['Genişlik']) == 'nan' or
            str(row['Renk']) == 'nan' or str(row['Model']) == 'nan'
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


# ─── Çıktı üretme & indirme UI ──────────────────────────

def build_zip(orders_df, ts, source_label):
    pdf_buffer = create_pdf_labels(orders_df)
    lazer_pdf  = create_lazer_labels(orders_df)
    uretim_txt = create_uretim_listesi(orders_df)
    kisisel_txt = create_kisisellestime_listesi(orders_df)
    store_name = orders_df['Mağaza'].iloc[0] if len(orders_df) > 0 else ''
    kontrol_pdf = create_kontrol_listesi(orders_df, store_name)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"kargo_etiketleri_{ts}.pdf", pdf_buffer.getvalue())
        if lazer_pdf:
            zf.writestr(f"lazer_etiketleri_{ts}.pdf", lazer_pdf)
        zf.writestr(f"fsm_uretim_{ts}.txt", uretim_txt.encode('utf-8'))
        zf.writestr(f"kisisellestime_{ts}.txt", kisisel_txt.encode('utf-8'))
        zf.writestr(f"kontrol_{ts}.pdf", kontrol_pdf)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def render_download_row(orders_df, label_suffix, key_suffix):
    state_key = f"files_{key_suffix}"

    if state_key not in st.session_state:
        ts = datetime.now(ZoneInfo("Europe/Istanbul")).strftime('%Y%m%d_%H%M%S')
        store_name = orders_df['Mağaza'].iloc[0] if len(orders_df) > 0 else 'siparis'
        with st.spinner("Dosyalar oluşturuluyor..."):
            pdf_buffer = create_pdf_labels(orders_df)
            lazer_pdf  = create_lazer_labels(orders_df)
            uretim_txt = create_uretim_listesi(orders_df)
            kisisel_txt = create_kisisellestime_listesi(orders_df)
            kontrol_pdf = create_kontrol_listesi(orders_df, store_name)
            zip_data = build_zip(orders_df, ts, key_suffix)
        st.session_state[state_key] = {
            "ts": ts,
            "store_name": store_name,
            "pdf": pdf_buffer.getvalue(),
            "lazer": lazer_pdf,
            "uretim": uretim_txt.encode("utf-8"),
            "kisisel": kisisel_txt.encode("utf-8"),
            "kontrol": kontrol_pdf,
            "zip": zip_data,
        }

    f = st.session_state[state_key]
    ts = f["ts"]
    store_name = f["store_name"]
    has_lazer = f["lazer"] is not None

    st.download_button(
        f"📦 {label_suffix} — TÜM DOSYALARI İNDİR (.zip)",
        data=f["zip"],
        file_name=f"{store_name}_{ts}.zip",
        mime="application/zip",
        key=f"dl_zip_{key_suffix}",
        type="primary",
        use_container_width=True
    )

    st.markdown("**Ayrı ayrı indir:**")
    num_cols = 5 if has_lazer else 4
    cols = st.columns(num_cols)
    with cols[0]:
        st.download_button("📄 Kargo Etiketleri", data=f["pdf"],
            file_name=f"kargo_{ts}.pdf", mime="application/pdf",
            key=f"dl_pdf_{key_suffix}", use_container_width=True)
    if has_lazer:
        with cols[1]:
            st.download_button("🟠 Lazer Etiketleri", data=f["lazer"],
                file_name=f"lazer_{ts}.pdf", mime="application/pdf",
                key=f"dl_lazer_{key_suffix}", use_container_width=True)
    with cols[-3]:
        st.download_button("📝 Üretim Listesi", data=f["uretim"],
            file_name=f"uretim_{ts}.txt", mime="text/plain",
            key=f"dl_uretim_{key_suffix}", use_container_width=True)
    with cols[-2]:
        st.download_button("✍️ Kişiselleştirme", data=f["kisisel"],
            file_name=f"kisisel_{ts}.txt", mime="text/plain",
            key=f"dl_kisisel_{key_suffix}", use_container_width=True)
    with cols[-1]:
        st.download_button("📋 Kontrol Listesi", data=f["kontrol"],
            file_name=f"kontrol_{ts}.pdf", mime="application/pdf",
            key=f"dl_kontrol_{key_suffix}", use_container_width=True)

    if st.button("🔄 Yeniden oluştur", key=f"regen_{key_suffix}"):
        del st.session_state[state_key]
        st.rerun()


def process_and_render(df, source_label=""):
    with st.spinner("Siparişler işleniyor..."):
        orders_df = parse_csv(df)

    coklu_count = orders_df['Çoklu'].sum() if 'Çoklu' in orders_df.columns else 0
    coklu_text = f" ({int(coklu_count)} çiftli sipariş)" if coklu_count > 0 else ""
    st.success(f"✅ {len(orders_df)} sipariş işlendi!{coklu_text} {source_label}")

    with st.spinner("Sipariş listesi güncelleniyor..."):
        sonuc = load_orders_to_session(orders_df)
        if sonuc is False:
            st.warning("⚠️ Google Sheets bağlantısı kurulamadı.")
        else:
            st.success(f"✅ {sonuc} yeni sipariş takip listesine eklendi.")

    st.markdown("#### 📋 İşlenmiş Siparişler")
    st.markdown("""<style>
    [data-testid="stDataEditor"] td, [data-testid="stDataEditor"] th { font-size: 12px !important; }
    </style>""", unsafe_allow_html=True)
    st.caption("Tablodaki hücreleri tıklayarak düzenleyebilirsiniz. Düzenledikten sonra o satır için çıktı alabilirsiniz.")

    edit_cols = ['Seç', 'Sipariş No', 'Müşteri', 'Model', 'Renk', 'Genişlik', 'Ölçü', 'Kişiselleştirme', 'Özel Not']
    available_data_cols = [c for c in edit_cols[1:] if c in orders_df.columns]

    # Satır ekle butonu
    if st.button("➕ Boş satır ekle", key=f"add_row_{source_label}"):
        empty = {c: '' for c in orders_df.columns}
        empty['Çoklu'] = False
        orders_df = pd.concat([orders_df, pd.DataFrame([empty])], ignore_index=True)
        st.session_state[f"orders_df_{source_label}"] = orders_df.copy()
        st.rerun()

    display_df = orders_df[available_data_cols].copy()
    display_df.insert(0, 'Seç', False)
    # Çiftli siparişleri işaretle
    if 'Çoklu' in orders_df.columns:
        def row_icon(row):
            ozel = str(row.get('Özel Not', '') or '').upper()
            if 'GEÇİLDİ' in ozel or 'GECILDI' in ozel:
                return '✅'
            if row.get('Çoklu'):
                return '👥'
            return ''
        display_df.insert(1, '⚡', orders_df.apply(row_icon, axis=1))

    edited_df = st.data_editor(
        display_df,
        use_container_width=True,
        num_rows="fixed",
        key=f"editor_{source_label}",
        hide_index=True,
        column_config={
            'Seç':              st.column_config.CheckboxColumn('Seç', width='small'),
            '⚡':               st.column_config.TextColumn('', width='small'),
            'Sipariş No':       st.column_config.TextColumn('Sipariş No', width='small'),
            'Müşteri':          st.column_config.TextColumn('Müşteri', width='small'),
            'Model':            st.column_config.SelectboxColumn('Model', options=['BOMBE','ÇATI','ÇATI MAT','DÜZ','TEKTAŞ','FANTAZİ','YENİLEME',''], width='medium'),
            'Renk':             st.column_config.SelectboxColumn('Renk', options=['BEYAZ','MAT BEYAZ','SARI','MAT SARI','ROSE','MAT ROSE',''], width='small'),
            'Genişlik':         st.column_config.SelectboxColumn('Genişlik', options=['2MM','3MM','4MM','5MM','6MM','7MM','8MM',''], width='small'),
            'Ölçü':             st.column_config.TextColumn('Ölçü', width='small'),
            'Kişiselleştirme':  st.column_config.TextColumn('Kişiselleştirme', width='large'),
            'Özel Not':         st.column_config.TextColumn('Özel Not', width='large'),
        }
    )

    # Düzenlenmiş değerleri orders_df'e yansıt (yeni satırlar dahil)
    edited_data = edited_df.drop(columns=['Seç', '⚡'], errors='ignore').reset_index(drop=True)
    if len(edited_data) > len(orders_df):
        # Yeni satırlar eklendi, orders_df'i genişlet
        extra = len(edited_data) - len(orders_df)
        template = orders_df.iloc[0].copy() if len(orders_df) > 0 else {}
        for _ in range(extra):
            empty = {c: '' for c in orders_df.columns}
            empty['Çoklu'] = False
            orders_df = pd.concat([orders_df, pd.DataFrame([empty])], ignore_index=True)
    orders_df = orders_df.iloc[:len(edited_data)].reset_index(drop=True)
    for col in available_data_cols:
        if col in edited_data.columns:
            orders_df[col] = edited_data[col].values

    # Özet
    gecildi_count = orders_df['Özel Not'].apply(
        lambda x: 'GEÇİLDİ' in str(x).upper() or 'GECILDI' in str(x).upper()
    ).sum() if 'Özel Not' in orders_df.columns else 0

    st.markdown("### 📊 Özet")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Toplam Sipariş", len(orders_df))
    with c2: st.metric("Kişiselleştirme", orders_df['Kişiselleştirme'].notna().sum())
    with c3: st.metric("Farklı Model", orders_df['Model'].nunique())
    with c4: st.metric("Yenileme", len(orders_df[orders_df['Model'] == 'YENİLEME']))
    with c5: st.metric("✅ Geçildi", int(gecildi_count))

    # orders_df'i session'a kaydet
    st.session_state[f"orders_df_{source_label}"] = orders_df.copy()

    # Seçili satırları sil
    selected_mask = edited_df['Seç'] == True
    selected_indices = edited_df.index[selected_mask].tolist()
    if selected_indices:
        if st.button(f"🗑️ Seçili {len(selected_indices)} satırı sil", key=f"del_rows_{source_label}", type="secondary"):
            orders_df = orders_df.drop(index=selected_indices).reset_index(drop=True)
            st.session_state[f"orders_df_{source_label}"] = orders_df.copy()
            for k in [f"files_all_{source_label}", f"files_sel_{source_label}", f"sel_indices_{source_label}"]:
                if k in st.session_state: del st.session_state[k]
            st.rerun()

    # Seçili satırlar için çıktı

    st.markdown("### 🎯 Çıktı Al")
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        sel_label = f"📄 Seçili {len(selected_indices)} Satır İçin Çıktı Al" if selected_indices else "📄 Seçili Satır Yok"
        if st.button(sel_label, key=f"selected_rows_{source_label}", type="primary",
                     disabled=not selected_indices, use_container_width=True):
            st.session_state[f"sel_indices_{source_label}"] = selected_indices
            if f"files_sel_{source_label}" in st.session_state:
                del st.session_state[f"files_sel_{source_label}"]
    with btn_col2:
        if st.button("🚀 Tüm Listeden Dosya Oluştur", type="primary", key=f"all_{source_label}",
                     use_container_width=True):
            if f"files_all_{source_label}" in st.session_state:
                del st.session_state[f"files_all_{source_label}"]

    if f"sel_indices_{source_label}" in st.session_state:
        idxs = st.session_state[f"sel_indices_{source_label}"]
        df_s = st.session_state[f"orders_df_{source_label}"]
        sel_df = df_s.iloc[idxs].copy()
        st.markdown(f"#### Seçili {len(idxs)} Satır")
        render_download_row(sel_df, f"Seçili {len(idxs)} Satır", f"sel_{source_label}")

    st.markdown("#### Tüm Liste")
    render_download_row(
        st.session_state[f"orders_df_{source_label}"],
        "Tüm Liste",
        f"all_{source_label}"
    )

# ─── Tab yapısı ─────────────────────────────────────────

st.markdown("""
<style>
[data-testid="stTabs"] [role="tablist"] { gap: 8px; }
[data-testid="stTabs"] button[role="tab"] {
    font-size: 1rem !important; font-weight: 700 !important;
    text-transform: uppercase !important; letter-spacing: 0.05em !important;
    padding: 10px 24px !important; border-radius: 8px 8px 0 0 !important;
}
[data-testid="stTabs"] button[role="tab"]:nth-child(1) { background-color: #1a3a5c !important; color: white !important; }
[data-testid="stTabs"] button[role="tab"]:nth-child(1)[aria-selected="true"] { background-color: #2d6aa0 !important; border-bottom: 3px solid #5ba3d9 !important; }
[data-testid="stTabs"] button[role="tab"]:nth-child(2) { background-color: #5c1a1a !important; color: white !important; }
[data-testid="stTabs"] button[role="tab"]:nth-child(2)[aria-selected="true"] { background-color: #a03030 !important; border-bottom: 3px solid #e07070 !important; }
</style>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📦 SİPARİŞ YÜKLE & DOSYALAR", "🚨 SORUNLU SİPARİŞ TAKİBİ"])

# ─── TAB 1 ──────────────────────────────────────────────
with tab1:
    col_main, col_info = st.columns([3, 1])

    with col_info:
        st.markdown("### ℹ️ Bilgi")
        st.info("""
        **API Mağazaları:**
        - 🔵 Chepniq
        - 🔴 Foria
        - 🟢 Cerasus

        Her mağaza için ayrı buton ile bekleyen siparişler çekilir.

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
        # ── API Bölümü ───────────────────────────────────
        st.markdown("### 🔌 API ile Sipariş Getir")

        api_stores = [
            ("CPQ", "🔵 Chepniq"),
            ("FRY", "🔴 Foria"),
            ("CRSS", "🟢 Cerasus"),
        ]

        api_cols = st.columns(3)
        for i, (store_code, btn_label) in enumerate(api_stores):
            with api_cols[i]:
                if st.button(btn_label + " Siparişlerini Getir", key=f"api_btn_{store_code}", type="primary", use_container_width=True):
                    for k in list(st.session_state.keys()):
                        if f"api_{store_code}" in k:
                            st.session_state.pop(k, None)
                    with st.spinner(f"{store_code} siparişleri çekiliyor..."):
                        api_df = fetch_pending_orders_for_store(store_code)
                    if api_df is not None and not api_df.empty:
                        st.session_state[f"api_df_{store_code}"] = api_df
                        st.session_state[f"api_ready_{store_code}"] = True
                        st.rerun()
                    elif api_df is not None and api_df.empty:
                        st.warning(f"{store_code}: Bekleyen sipariş yok.")
                if st.session_state.get(f"api_ready_{store_code}"):
                    n = len(st.session_state.get(f"api_df_{store_code}", []))
                    st.success(f"✅ {n} satır hazır")

        st.markdown("---")

        store_colors = {
            "CPQ":  ("#1a3a5c", "#d6e4f0"),
            "FRY":  ("#8b0000", "#f5d5d5"),
            "CRSS": ("#1a5c2a", "#d5f0dc"),
        }
        for store_code, btn_label in api_stores:
            if st.session_state.get(f"api_ready_{store_code}") and st.session_state.get(f"api_df_{store_code}") is not None:
                hdr, bg = store_colors.get(store_code, ("#333", "#f5f5f5"))
                n = len(st.session_state[f"api_df_{store_code}"])
                st.markdown(
                    f'''<div style="background:{hdr};color:white;padding:8px 16px;border-radius:8px 8px 0 0;font-weight:600;font-size:15px;margin-bottom:0">
                    📋 {store_code} Siparişleri &nbsp;<span style="font-weight:400;font-size:13px;opacity:0.85">({n} sipariş)</span></div>
                    <style>
                    section[data-testid="stExpander"] div[data-testid="stExpanderDetails"] * {{
                        color: inherit;
                    }}
                    </style>''',
                    unsafe_allow_html=True
                )
                st.markdown(f'<style>div[data-testid="stExpander"] summary p {{ color: {hdr} !important; font-weight: 700 !important; }}</style>', unsafe_allow_html=True)
                with st.expander(f"📋 {store_code} Siparişleri ({n} sipariş)", expanded=True):
                    try:
                        process_and_render(st.session_state[f"api_df_{store_code}"], source_label=f"api_{store_code}")
                    except Exception as e:
                        st.error(f"İşleme hatası: {e}")
                st.markdown("---")

        # ── Excel / CSV yükleme ──────────────────────────
        st.markdown("### 📂 Excel / CSV Yükle")
        uploaded_file = st.file_uploader(
            "📦 Dosyayı buraya sürükleyin veya tıklayın",
            type=['csv', 'xlsx', 'xlsm'],
            key="file_uploader_main"
        )

    if uploaded_file:
        with col_main:
            try:
                file_key = f"file_{uploaded_file.name}_{uploaded_file.size}"
                if st.session_state.get("last_file_key") != file_key:
                    for k in list(st.session_state.keys()):
                        if k.endswith("_xlsx"):
                            st.session_state.pop(k, None)
                    st.session_state["last_file_key"] = file_key

                df, file_type = load_file(uploaded_file)
                st.success(f"✅ {len(df)} satır yüklendi ({'XLSX' if file_type == 'xlsx' else 'CSV'})")
                process_and_render(df, source_label="xlsx")

            except Exception as e:
                st.error(f"❌ Hata: {str(e)}")


# ─── TAB 2 ──────────────────────────────────────────────
with tab2:
    st.markdown("### 🚨 Sorunlu Sipariş Takibi")

    col_r, _ = st.columns([1, 5])
    with col_r:
        if st.button("🔄 Yenile", key="refresh_sheet"):
            get_gsheet.clear()

    st.markdown("---")
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

        def parse_tarih(t):
            try: return pd.to_datetime(str(t), format="%d.%m.%Y %H:%M")
            except: return pd.Timestamp.max

        tarih_col = "Güncelleme Saati" if "Güncelleme Saati" in goster_df.columns else None
        if tarih_col:
            goster_df["_sort"] = goster_df[tarih_col].apply(parse_tarih)
            goster_df = goster_df.sort_values("_sort", ascending=True).drop(columns=["_sort"])
        st.markdown(f"**{len(goster_df)} kayıt**")
    else:
        goster_df = pd.DataFrame(columns=SHEET_COLS)
        st.info("Henüz sipariş yüklenmemiş.")

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
        not_ozet = (" — " + not_text[:50] + ("..." if len(not_text) > 50 else "")) if has_problem else ""

        label = f"{icon} #{siparis_no} [{row.get('Mağaza','')}] — {musteri} | {genislik} {model} {olcu}"
        if has_problem:
            label += f" | {durum_icon} {durum}{not_ozet}"

        with st.expander(label):
            if has_problem and (ekleyen.strip() not in ["","nan"] or guncelleme.strip() not in ["","nan"]):
                st.caption(f"Son düzenleyen: {ekleyen} | {guncelleme}")

            col_a, col_b = st.columns([2, 1])
            with col_a:
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
                ek_not = st.text_area("Ek Not", value=mevcut_aciklama,
                    key=f"not_{siparis_no}_{idx}", height=80)
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

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <b>🏭 Sipariş Takip Sistemi v4.0</b><br>
    CPQ + FRY + CRSS API → Düzenlenebilir Tablo → PDF Etiket + Lazer + Üretim + Kişiselleştirme + Kontrol
</div>
""", unsafe_allow_html=True)
