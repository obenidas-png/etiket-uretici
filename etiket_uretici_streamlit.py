"""
ETSY ATÖLYE YÖNETİM SİSTEMİ - Streamlit Uygulaması
CSV veya XLSX Yükle → PDF Etiket + 3 TXT Listesi Oluştur
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black
import re

st.set_page_config(
    page_title="Etsy Atölye Yönetim",
    page_icon="🏭",
    layout="wide"
)

st.markdown("""
<style>
    .main-title {
        text-align: center;
        padding: 20px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        color: white;
        margin-bottom: 30px;
    }
    .stButton>button {
        width: 100%;
        background-color: #667eea;
        color: white;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-title">🏭 Etsy Atölye Yönetim Sistemi</h1>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# XLSX → ortak DataFrame dönüştürücü
# ─────────────────────────────────────────────
def xlsx_to_standard_df(df_xlsx):
    """
    XLSX sütunlarını parse_csv'nin beklediği CSV sütun adlarına dönüştürür.
    Options Name/Value 1-2-3 → Özellikler sütununa çevrilir.
    """
    rows = []
    for _, row in df_xlsx.iterrows():
        # Options'ları Özellikler formatına çevir (Ad:X, Değer:Y, ...)
        ozellikler_parts = []
        for i in range(1, 4):
            name = row.get(f'Options Name {i}')
            value = row.get(f'Options Value {i}')
            if pd.notna(name) and pd.notna(value):
                ozellikler_parts.append(f"Ad:{name}, Değer:{value}")
        ozellikler = ", ".join(ozellikler_parts)

        # Notes - From Buyer varsa Kişiselleştirme olarak kullan
        buyer_note = str(row.get('Notes - From Buyer', '') or '')

        rows.append({
            'MagazaAdı':       row.get('Market - Store Name', ''),
            'SiparişNumarası': row.get('Order - Number', ''),
            'Alıcı':           row.get('Ship To - Name', ''),
            'ÜrünAdı':         row.get('Item - Name', ''),
            'Özellikler':      ozellikler if ozellikler else None,
            # Ek XLSX alanları (parse_csv'de props üzerinden erişilir)
            '_BuyerNote':      buyer_note,
            '_GiftMessage':    str(row.get('Gift - Message', '') or ''),
            '_ShipBy':         str(row.get('Date - Ship By Date', '') or ''),
            '_OrderTotal':     row.get('Amount - Order Total', ''),
        })
    return pd.DataFrame(rows)


def load_file(uploaded_file):
    """Yüklenen dosyayı (CSV veya XLSX) standart DataFrame'e çevirir."""
    name = uploaded_file.name.lower()
    if name.endswith('.xlsx') or name.endswith('.xlsm'):
        df_raw = pd.read_excel(uploaded_file, engine='openpyxl')
        return xlsx_to_standard_df(df_raw), 'xlsx'
    else:
        return pd.read_csv(uploaded_file), 'csv'


# ─────────────────────────────────────────────
# Mevcut fonksiyonlar (değiştirilmedi)
# ─────────────────────────────────────────────
def parse_csv(df):
    orders = []

    def get_store_code(store_name):
        store_lower = str(store_name).lower()
        if 'foria' in store_lower:
            return 'FRY'
        elif 'chepniq' in store_lower:
            return 'CPQ'
        elif 'cerasus' in store_lower:
            return 'CRSS'
        else:
            return store_name[:4].upper()

    for idx, row in df.iterrows():
        store_name = str(row.get('MagazaAdı', ''))
        store_code = get_store_code(store_name)

        product = str(row.get('ÜrünAdı', ''))
        product_lower = product.lower()

        if any(keyword in product_lower for keyword in [
            'price adjustment', 'shipping fee', 'shipping cost',
            'additional fee', 'extra charge'
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

        # XLSX'ten gelen ek alanları props'a ekle
        if row.get('_BuyerNote'):
            props.setdefault('Personalization', row['_BuyerNote'])

        if 'cerasus' in store_name.lower():
            product_clean = product.split(' - ')[0]
            if len(product_clean) > 40:
                product_clean = product_clean[:37] + "..."

            color = props.get('Metal', '')
            if not color:
                if '14k yellow gold' in product_lower or 'yellow gold' in product_lower:
                    color = '14K Yellow Gold'
                elif '14k white gold' in product_lower or 'white gold' in product_lower:
                    color = '14K White Gold'
                elif '14k rose gold' in product_lower or 'rose gold' in product_lower:
                    color = '14K Rose Gold'
                elif 'sterling silver' in product_lower or 'silver' in product_lower:
                    color = 'Sterling Silver'

            orders.append({
                'Mağaza': store_code,
                'Sipariş No': row.get('SiparişNumarası', ''),
                'Müşteri': row.get('Alıcı', ''),
                'Genişlik': '',
                'Renk': color,
                'Model': '',
                'Ölçü': '',
                'Kişiselleştirme': props.get('Personalization', ''),
                'Ürün': product_clean
            })
        else:
            model = ''
            color = ''
            width = props.get('Width', props.get('Band Width', ''))

            if 'white gold' in product_lower or 'beyaz' in product_lower:
                color = 'BEYAZ'
            elif 'yellow gold' in product_lower or 'sarı' in product_lower or 'gold filled' in product_lower:
                color = 'SARI'

            if 'resizing' in product_lower or 'size adjustment' in product_lower or 'replacement' in product_lower:
                model = 'YENİLEME'
            elif 'bevel' in product_lower:
                model = 'ÇATI MAT' if ('matte' in product_lower or 'mat' in product_lower) else 'ÇATI'
            elif 'dome' in product_lower:
                model = 'BOMBE'
            elif 'flat' in product_lower:
                model = 'DÜZ'
            elif 'oval' in product_lower or 'solitaire' in product_lower:
                model = 'OVAL TEKTAŞ'

            if not width:
                width_match = re.search(r'(\d+)\s*mm', product_lower)
                if width_match:
                    width = width_match.group(1) + 'MM'
            else:
                width = str(width).strip()
                if 'mm' not in width.lower():
                    width = width.upper() + 'MM'
                else:
                    width = width.upper()

            ring_size = props.get('Ring size', props.get('Size for You', ''))

            if 'set of 2' in product_lower or 'Size for Your Partner' in props:
                size1 = props.get('Size for You', '')
                size2 = props.get('Size for Your Partner', '')

                width1 = '2MM'
                width2 = '4MM'

                personalization = props.get('Personalization', '')
                if personalization:
                    pers_lower = personalization.lower()
                    hers_match = re.search(r'hers[^:]*:\s*(\d+)\s*mm', pers_lower)
                    his_match = re.search(r'his[^:]*:\s*(\d+)\s*mm', pers_lower)
                    if hers_match:
                        width1 = hers_match.group(1) + 'MM'
                    if his_match:
                        width2 = his_match.group(1) + 'MM'

                if width1 == '2MM' or width2 == '4MM':
                    if 'hers' in product_lower and 'his' in product_lower:
                        hers_match = re.search(r'hers[^:]*:\s*(\d+)\s*mm', product_lower)
                        his_match = re.search(r'his[^:]*:\s*(\d+)\s*mm', product_lower)
                        if hers_match:
                            width1 = hers_match.group(1) + 'MM'
                        if his_match:
                            width2 = his_match.group(1) + 'MM'
                    elif '2mm' in product_lower and '4mm' in product_lower:
                        width1 = '2MM'
                        width2 = '4MM'
                    elif width:
                        width1 = width
                        width2 = width

                if size1:
                    orders.append({
                        'Mağaza': store_code,
                        'Sipariş No': row.get('SiparişNumarası', ''),
                        'Müşteri': row.get('Alıcı', ''),
                        'Genişlik': width1,
                        'Renk': color,
                        'Model': model,
                        'Ölçü': size1,
                        'Kişiselleştirme': props.get('Personalization', ''),
                        'Ürün': product
                    })
                if size2:
                    orders.append({
                        'Mağaza': store_code,
                        'Sipariş No': row.get('SiparişNumarası', ''),
                        'Müşteri': row.get('Alıcı', ''),
                        'Genişlik': width2,
                        'Renk': color,
                        'Model': model,
                        'Ölçü': size2,
                        'Kişiselleştirme': props.get('Personalization', ''),
                        'Ürün': product
                    })
            else:
                orders.append({
                    'Mağaza': store_code,
                    'Sipariş No': row.get('SiparişNumarası', ''),
                    'Müşteri': row.get('Alıcı', ''),
                    'Genişlik': width.upper() if width else '',
                    'Renk': color,
                    'Model': model.upper() if model else '',
                    'Ölçü': ring_size,
                    'Kişiselleştirme': props.get('Personalization', ''),
                    'Ürün': product
                })

    return pd.DataFrame(orders)


def create_pdf_labels(orders_df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4

    label_width = 5 * cm
    label_height = 3 * cm
    margin_x = 0.2 * cm
    margin_y = 0.2 * cm
    gap_x = 0.15 * cm
    gap_y = 0.15 * cm
    labels_per_row = 4
    labels_per_column = 9
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
    def turkce_to_ascii(text):
        if not text or pd.isna(text):
            return ''
        text = str(text)
        replacements = {
            'ı': 'i', 'İ': 'I', 'ş': 's', 'Ş': 'S',
            'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U',
            'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
        }
        for tr_char, ascii_char in replacements.items():
            text = text.replace(tr_char, ascii_char)
        return text

    c.setStrokeColor(black)
    c.setLineWidth(1)
    c.rect(x, y, width, height)

    text_x = x + 0.1 * cm
    font_size = 7

    store = str(data.get('Mağaza', '')).lower()

    if 'cerasus' in store or store == 'crss':
        line_height = height / 7
        for i in range(1, 7):
            c.setLineWidth(0.3)
            c.line(x, y + (i * line_height), x + width, y + (i * line_height))

        note = ''
        if pd.notna(data.get('Kişiselleştirme')):
            note = str(data['Kişiselleştirme'])
            note = note.replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
            note = turkce_to_ascii(note[:30])

        rows = [
            ('Magaza', 'CRSS'),
            ('Siparis No', str(data['Sipariş No'])),
            ('Musteri', turkce_to_ascii(str(data['Müşteri'])[:20])),
            ('Urun', turkce_to_ascii(str(data['Ürün'])[:25])),
            ('Zincir', ''),
            ('Renk', turkce_to_ascii(str(data['Renk'])[:15])),
            ('Not', note)
        ]
    else:
        line_height = height / 7
        for i in range(1, 7):
            c.setLineWidth(0.3)
            c.line(x, y + (i * line_height), x + width, y + (i * line_height))

        pers_text = ''
        if pd.notna(data['Kişiselleştirme']):
            pers_text = str(data['Kişiselleştirme'])
            pers_text = pers_text.replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&')
            pers_text = pers_text[:30]

        rows = [
            ('Magaza', str(data.get('Mağaza', 'CPQ'))),
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
        value_x = x + 1.7 * cm
        try:
            c.drawString(value_x, row_y, str(value))
        except Exception:
            c.drawString(value_x, row_y, turkce_to_ascii(str(value)))


def create_uretim_listesi(orders_df):
    production = orders_df[orders_df['Model'] != 'YENİLEME'].copy()
    output = "Üretim Listesi\n==============\n\n"
    output += f"{'Genişlik':<10}{'Model':<15}{'Ölçü':<15}\n"
    output += f"{'-'*9} {'-'*14} {'-'*14}\n"
    for _, row in production.iterrows():
        output += f"{row['Genişlik']:<10}{row['Model']:<15}{row['Ölçü']:<15}\n"
    return output


def create_kisisellestime_listesi(orders_df):
    personalized = orders_df[orders_df['Kişiselleştirme'].notna() & (orders_df['Kişiselleştirme'] != '')].copy()
    if len(personalized) == 0:
        return "Kişiselleştirme gerektiren sipariş yok."
    output = "Kişiselleştirme Listesi\n=======================\n\n"
    for _, row in personalized.iterrows():
        text = str(row['Kişiselleştirme'])
        text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&').replace('\\n', '\n   ')
        output += f"Müşteri: {row['Müşteri']}\n"
        output += f"Genişlik: {row['Genişlik']}\n"
        output += f"Kişiselleştirme:\n   {text}\n"
        output += "-" * 80 + "\n\n"
    return output


def create_kontrol_listesi(orders_df, store_name=''):
    output = f"Mağaza Adı: {store_name}\nKontrol Listesi\n" + "=" * 170 + "\n\n"
    output += f"{'Sipariş No':<15} {'Müşteri Adı':>25} {'Genişlik':>9} {'Renk':>6} {'Model':>10} {'Ölçü':>10} "
    output += f"{'Kişiselleştirme':>90} {'CHECK':>8}\n"
    output += "-" * 170 + "\n"
    for _, row in orders_df.iterrows():
        pers = ''
        if pd.notna(row['Kişiselleştirme']):
            pers = str(row['Kişiselleştirme'])
            pers = pers.replace('&quot;', '"').replace('&#39;', "'").replace('&amp;', '&').replace('\\n', ' ')
            pers = pers[:100]
        output += (
            f"{str(row['Sipariş No']):<15} {str(row['Müşteri'])[:25]:>25} "
            f"{str(row['Genişlik']):>9} {str(row['Renk']):>6} {str(row['Model'])[:10]:>10} "
            f"{str(row['Ölçü']):>10} {pers:>90} {'[  ]':>8}\n"
        )
        output += "-" * 170 + "\n"
    return output


# ─────────────────────────────────────────────
# Ana uygulama
# ─────────────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 📤 Sipariş Dosyası Yükle")
    uploaded_file = st.file_uploader(
        "CSV veya XLSX dosyasını seçin",
        type=['csv', 'xlsx', 'xlsm'],
        help="Etsy'den export ettiğiniz CSV veya orders-detail-product.xlsx dosyasını yükleyin"
    )

with col2:
    st.markdown("### ℹ️ Bilgi")
    st.info("""
    **Desteklenen formatlar:**
    - 📄 Etsy CSV export
    - 📊 orders-detail-product.xlsx

    **Oluşacak Dosyalar:**
    - 📄 PDF Etiketler (3x5cm)
    - 📝 Üretim Listesi
    - 📝 Kişiselleştirme Listesi
    - 📝 Kontrol Listesi
    """)

if uploaded_file:
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
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Toplam Sipariş", len(orders_df))
        with col2:
            st.metric("Kişiselleştirme", orders_df['Kişiselleştirme'].notna().sum())
        with col3:
            st.metric("Farklı Model", orders_df['Model'].nunique())
        with col4:
            st.metric("Yenileme", len(orders_df[orders_df['Model'] == 'YENİLEME']))

        st.markdown("### 🎨 Dosyaları Oluştur")

        if not st.session_state.get('files_created', False):
            if st.button("🚀 TÜM DOSYALARI OLUŞTUR", type="primary"):
                with st.spinner("Dosyalar oluşturuluyor..."):
                    pdf_buffer = create_pdf_labels(orders_df)
                    uretim_txt = create_uretim_listesi(orders_df)
                    kisisel_txt = create_kisisellestime_listesi(orders_df)
                    store_name = orders_df['Mağaza'].iloc[0] if len(orders_df) > 0 else ''
                    kontrol_txt = create_kontrol_listesi(orders_df, store_name)

                    st.session_state['pdf_ready'] = pdf_buffer.getvalue()
                    st.session_state['uretim_ready'] = uretim_txt.encode('utf-8')
                    st.session_state['kisisel_ready'] = kisisel_txt.encode('utf-8')
                    st.session_state['kontrol_ready'] = kontrol_txt.encode('utf-8')
                    st.session_state['files_created'] = True
                    st.session_state['ts'] = datetime.now().strftime('%Y%m%d_%H%M%S')
                st.rerun()

        else:
            st.success("✅ Tüm dosyalar hazır!")
            ts = st.session_state.get('ts', 'dosya')
            st.markdown("### 📥 Dosyaları İndir")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.download_button(
                    label="📥 PDF Etiketler",
                    data=st.session_state['pdf_ready'],
                    file_name=f"etiketler_{ts}.pdf",
                    mime="application/pdf",
                    key="dl_pdf"
                )
            with col2:
                st.download_button(
                    label="📥 Üretim Listesi",
                    data=st.session_state['uretim_ready'],
                    file_name=f"uretim_{ts}.txt",
                    mime="text/plain",
                    key="dl_uretim"
                )
            with col3:
                st.download_button(
                    label="📥 Kişiselleştirme",
                    data=st.session_state['kisisel_ready'],
                    file_name=f"kisisellestime_{ts}.txt",
                    mime="text/plain",
                    key="dl_kisisel"
                )
            with col4:
                st.download_button(
                    label="📥 Kontrol Listesi",
                    data=st.session_state['kontrol_ready'],
                    file_name=f"kontrol_{ts}.txt",
                    mime="text/plain",
                    key="dl_kontrol"
                )

            st.markdown("---")
            if st.button("🔄 Yeni Dosya Yükle", type="secondary"):
                for k in ['files_created', 'pdf_ready', 'uretim_ready', 'kisisel_ready', 'kontrol_ready', 'ts', 'last_file_name']:
                    st.session_state.pop(k, None)
                st.rerun()

    except Exception as e:
        st.error(f"❌ Hata: {str(e)}")
        st.info("💡 CSV için gerekli sütunlar: MagazaAdı, Alıcı, SiparişNumarası, ÜrünAdı, Özellikler")
        st.info("💡 XLSX için: orders-detail-product formatında ShipStation export olmalı")

else:
    st.info("👆 CSV veya XLSX dosyanızı yükleyin")

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <b>🏭 Etsy Atölye Yönetim Sistemi v1.1</b><br>
    CSV + XLSX → PDF Etiket + 3 TXT Liste
</div>
""", unsafe_allow_html=True)
