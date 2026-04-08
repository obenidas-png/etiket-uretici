"""
ETSY ATÖLYE YÖNETİM SİSTEMİ - Streamlit Uygulaması
CSV Yükle → PDF Etiket + 3 TXT Listesi Oluştur
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

# Sayfa ayarları
st.set_page_config(
    page_title="Etsy Atölye Yönetim",
    page_icon="🏭",
    layout="wide"
)

# CSS
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

# Fonksiyonlar
def parse_csv(df):
    """CSV'yi işle ve sipariş listesi oluştur"""
    orders = []
    
    for idx, row in df.iterrows():
        # Özellikler sütununu parse et
        props = {}
        if pd.notna(row.get('Özellikler')):
            parts = str(row['Özellikler']).split(',')
            for i in range(0, len(parts), 2):
                if i+1 < len(parts):
                    key = parts[i].replace('Ad:', '').strip()
                    value = parts[i+1].replace('Değer:', '').strip()
                    props[key] = value
        
        # Ürün bilgileri
        product = str(row.get('ÜrünAdı', ''))
        
        # Model ve renk tespiti
        model = ''
        color = ''
        width = props.get('Width', '')
        
        product_lower = product.lower()
        
        # Renk
        if 'white gold' in product_lower or 'beyaz' in product_lower:
            color = 'BEYAZ'
        elif 'yellow gold' in product_lower or 'sarı' in product_lower or 'gold filled' in product_lower:
            color = 'SARI'
        
        # Model
        if 'resizing' in product_lower or 'size adjustment' in product_lower:
            model = 'YENİLEME'
        elif 'bevel' in product_lower:
            model = 'ÇATI'
            if 'matte' in product_lower or 'mat' in product_lower:
                model = 'ÇATI MAT'
        elif 'dome' in product_lower:
            model = 'BOMBE'
        elif 'flat' in product_lower:
            model = 'DÜZ'
        elif 'oval' in product_lower or 'solitaire' in product_lower:
            model = 'OVAL TEKTAŞ'
        
        # Genişlik
        if not width:
            width_match = re.search(r'(\d+)\s*mm', product_lower)
            if width_match:
                width = width_match.group(1) + 'MM'
        elif width and 'mm' not in width.lower():
            width = width + 'MM'
        
        # Ring size
        ring_size = props.get('Ring size', props.get('Size for You', ''))
        
        # Çift yüzük kontrolü (Set of 2)
        if 'set of 2' in product_lower or 'Size for Your Partner' in props:
            size1 = props.get('Size for You', '')
            size2 = props.get('Size for Your Partner', '')
            
            # 2mm ve 4mm tespiti
            if '2mm' in product_lower:
                width1 = '2MM'
                width2 = '4MM'
            else:
                width1 = width
                width2 = width
            
            # İki ayrı sipariş oluştur
            if size1:
                orders.append({
                    'Mağaza': row.get('MagazaAdı', ''),
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
                    'Mağaza': row.get('MagazaAdı', ''),
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
            # Tek sipariş
            orders.append({
                'Mağaza': row.get('MagazaAdı', ''),
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
    """PDF etiketleri oluşturur"""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    
    label_width = 5 * cm
    label_height = 3 * cm
    margin_x = 1 * cm
    margin_y = 1 * cm
    
    labels_per_row = 4
    labels_per_column = 9
    labels_per_page = labels_per_row * labels_per_column
    
    label_count = 0
    
    for idx, row in orders_df.iterrows():
        col = label_count % labels_per_row
        row_num = (label_count // labels_per_row) % labels_per_column
        
        if label_count > 0 and label_count % labels_per_page == 0:
            c.showPage()
        
        x = margin_x + (col * label_width)
        y = page_height - margin_y - ((row_num + 1) * label_height)
        
        # Etiket çiz
        draw_label(c, x, y, label_width, label_height, row)
        label_count += 1
    
    c.save()
    buffer.seek(0)
    return buffer

def draw_label(c, x, y, width, height, data):
    """Tek etiket çizer"""
    c.setStrokeColor(black)
    c.setLineWidth(1)
    c.rect(x, y, width, height)
    
    line_height = height / 7
    for i in range(1, 7):
        line_y = y + (i * line_height)
        c.setLineWidth(0.3)
        c.line(x, line_y, x + width, line_y)
    
    text_x = x + 0.1 * cm
    font_size = 7
    
    rows = [
        ('Sipariş No', str(data['Sipariş No'])),
        ('Müşteri Adı', str(data['Ürün'])[:25]),
        ('Genişlik', str(data['Genişlik'])),
        ('Model', f"{data['Model']} {data['Renk']}".strip()),
        ('Ölçü', str(data['Ölçü'])),
        ('Lazer', data['Kişiselleştirme'][:20] if pd.notna(data['Kişiselleştirme']) else ''),
        ('Not', '')
    ]
    
    for i, (label, value) in enumerate(rows):
        row_y = y + height - ((i + 0.65) * line_height)
        
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(text_x, row_y, label)
        
        c.setFont("Helvetica", font_size)
        value_x = x + 1.7 * cm
        c.drawString(value_x, row_y, str(value)[:20])

def create_uretim_listesi(orders_df):
    """Üretim listesi TXT oluşturur"""
    # YENİLEME siparişlerini hariç tut
    production = orders_df[orders_df['Model'] != 'YENİLEME'].copy()
    
    output = "Üretim Listesi\n"
    output += "==============\n\n"
    output += f"{'Genişlik':<10}{'Model':<15}{'Ölçü':<15}\n"
    output += f"{'-'*9} {'-'*14} {'-'*14}\n"
    
    for idx, row in production.iterrows():
        output += f"{row['Genişlik']:<10}{row['Model']:<15}{row['Ölçü']:<15}\n"
    
    return output

def create_kisisellestime_listesi(orders_df):
    """Kişiselleştirme listesi TXT oluşturur"""
    personalized = orders_df[orders_df['Kişiselleştirme'].notna()].copy()
    
    if len(personalized) == 0:
        return "Kişiselleştirme gerektiren sipariş yok."
    
    output = "Kişiselleştirme Listesi\n"
    output += "=======================\n\n"
    output += f"{'Müşteri Adı':>30} {'Yüzük Genişliği':>16} {'Kişiselleştirme Metni':>90}\n"
    
    for idx, row in personalized.iterrows():
        customer = str(row['Müşteri'])[:30]
        width = str(row['Genişlik'])
        text = str(row['Kişiselleştirme'])[:80]
        output += f"{customer:>30} {width:>16} {text:>90}\n"
    
    return output

def create_kontrol_listesi(orders_df, store_name=''):
    """Kontrol listesi TXT oluşturur"""
    output = f"Mağaza Adı: {store_name}\n"
    output += "Kontrol Listesi\n"
    output += "================================\n\n"
    output += f"{'Sipariş No':<15} {'Müşteri Adı':>25} {'Genişlik':>9} {'Renk':>6} {'Model':>10} {'Ölçü':>10} "
    output += f"{'Kişiselleştirme':>90} {'Check':>5}\n"
    
    for idx, row in orders_df.iterrows():
        order_no = str(row['Sipariş No'])
        customer = str(row['Müşteri'])[:25]
        width = str(row['Genişlik'])
        color = str(row['Renk'])
        model = str(row['Model'])[:10]
        size = str(row['Ölçü'])
        pers = str(row['Kişiselleştirme'])[:80] if pd.notna(row['Kişiselleştirme']) else ''
        
        output += f"{order_no:<15} {customer:>25} {width:>9} {color:>6} {model:>10} {size:>10} {pers:>90} {'☐':>5}\n"
    
    return output

# Ana uygulama
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 📤 CSV Dosyası Yükle")
    uploaded_file = st.file_uploader(
        "Etsy siparişlerinizi içeren CSV dosyasını seçin (order-detail.csv)",
        type=['csv'],
        help="Etsy'den export ettiğiniz order-detail.csv dosyasını yükleyin"
    )

with col2:
    st.markdown("### ℹ️ Bilgi")
    st.info("""
    **Oluşacak Dosyalar:**
    - 📄 PDF Etiketler (3x5cm)
    - 📝 Üretim Listesi
    - 📝 Kişiselleştirme Listesi
    - 📝 Kontrol Listesi
    """)

if uploaded_file:
    try:
        # CSV'yi oku
        df = pd.read_csv(uploaded_file)
        st.success(f"✅ {len(df)} ham sipariş yüklendi!")
        
        # İşle
        with st.spinner("Siparişler işleniyor..."):
            orders_df = parse_csv(df)
        
        st.success(f"✅ {len(orders_df)} sipariş işlendi!")
        
        # Önizleme
        with st.expander("📋 İşlenmiş Siparişler"):
            st.dataframe(orders_df)
        
        # İstatistikler
        st.markdown("### 📊 Özet")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Toplam Sipariş", len(orders_df))
        with col2:
            st.metric("Kişiselleştirme", orders_df['Kişiselleştirme'].notna().sum())
        with col3:
            st.metric("Farklı Model", orders_df['Model'].nunique())
        with col4:
            yenileme = len(orders_df[orders_df['Model'] == 'YENİLEME'])
            st.metric("Yenileme", yenileme)
        
        # Dosyaları oluştur
        st.markdown("### 🎨 Dosyaları Oluştur")
        
        if st.button("🚀 TÜM DOSYALARI OLUŞTUR", type="primary"):
            with st.spinner("Dosyalar oluşturuluyor..."):
                # PDF
                pdf_buffer = create_pdf_labels(orders_df)
                
                # TXT dosyaları
                uretim_txt = create_uretim_listesi(orders_df)
                kisisel_txt = create_kisisellestime_listesi(orders_df)
                store_name = orders_df['Mağaza'].iloc[0] if len(orders_df) > 0 else ''
                kontrol_txt = create_kontrol_listesi(orders_df, store_name)
            
            st.success("✅ Tüm dosyalar hazır!")
            st.balloons()
            
            # İndirme butonları
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📥 PDF Etiketler İndir",
                    data=pdf_buffer,
                    file_name=f"etiketler_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf"
                )
                
                st.download_button(
                    label="📥 Üretim Listesi İndir",
                    data=uretim_txt.encode('utf-8'),
                    file_name=f"uretim_listesi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
            
            with col2:
                st.download_button(
                    label="📥 Kişiselleştirme Listesi İndir",
                    data=kisisel_txt.encode('utf-8'),
                    file_name=f"kisisellestime_listesi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
                
                st.download_button(
                    label="📥 Kontrol Listesi İndir",
                    data=kontrol_txt.encode('utf-8'),
                    file_name=f"kontrol_listesi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
    
    except Exception as e:
        st.error(f"❌ Hata: {str(e)}")
        st.info("💡 Lütfen order-detail.csv formatında dosya yüklediğinizden emin olun.")

else:
    st.info("👆 Lütfen CSV dosyanızı yükleyin")

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <b>🏭 Etsy Atölye Yönetim Sistemi v1.0</b><br>
    CSV → PDF Etiket + 3 TXT Liste
</div>
""", unsafe_allow_html=True)
