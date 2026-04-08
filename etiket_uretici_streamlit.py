"""
ETSY ETİKET ÜRETİCİ - Streamlit Uygulaması
Excel yükle → PDF etiket indir
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
    page_title="Etsy Etiket Üretici",
    page_icon="🏷️",
    layout="centered"
)

# CSS
st.markdown("""
<style>
    .main-title {
        text-align: center;
        color: #2c3e50;
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
        padding: 10px;
        border-radius: 5px;
        border: none;
        font-weight: bold;
    }
    .info-box {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Başlık
st.markdown('<h1 class="main-title">🏷️ Etsy Etiket Üretici</h1>', unsafe_allow_html=True)

st.markdown("""
<div class="info-box">
📋 <b>Nasıl Kullanılır:</b><br>
1. Etsy siparişlerinizi Excel olarak yükleyin<br>
2. "PDF Etiket Oluştur" butonuna tıklayın<br>
3. Oluşan PDF'i indirin ve yazdırın<br>
<br>
<b>Format:</b> 3x5cm çerçeveli etiketler (A4 kağıda 4x9 = 36 etiket)
</div>
""", unsafe_allow_html=True)

# Fonksiyonlar
def extract_model_info(product_text):
    """Ürün adından model bilgilerini çıkarır"""
    info = {'model': 'Klasik', 'width': ''}
    
    product_lower = product_text.lower()
    
    # Model tespiti
    if 'bevel' in product_lower:
        info['model'] = 'Çatı'
    elif 'dome' in product_lower or 'bombe' in product_lower:
        info['model'] = 'Bombe'
    elif 'flat' in product_lower:
        info['model'] = 'Düz'
    
    # Genişlik
    width_match = re.search(r'(\d+)\s*mm', product_lower)
    if width_match:
        info['width'] = f"{width_match.group(1)}mm"
    
    return info

def create_pdf_labels(orders_df):
    """PDF etiketleri oluşturur"""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    
    # Etiket boyutları
    label_width = 5 * cm
    label_height = 3 * cm
    margin_x = 1 * cm
    margin_y = 1 * cm
    
    labels_per_row = 4
    labels_per_column = 9
    labels_per_page = labels_per_row * labels_per_column
    
    label_count = 0
    
    for idx, row in orders_df.iterrows():
        product = str(row.get('Ürün', ''))
        
        # Resizing service kontrolü
        is_resizing = 'resizing' in product.lower() or 'service' in product.lower()
        
        # Etiket verisi hazırla
        if is_resizing:
            label_data = {
                'Sipariş No': str(row.get('Sipariş No', row.get('Id', ''))),
                'Müşteri Adı': str(row.get('Müşteri', row.get('Alıcı', ''))),
                'Genişlik': '',
                'Model': 'Resizing',
                'Ölçü': str(row.get('Ring Size', '')),
                'Lazer': '',
                'Not': str(row.get('Kendi Notum', '')) if pd.notna(row.get('Kendi Notum')) else 'Ölçü Değişikliği'
            }
            ring_sizes = [label_data['Ölçü']]
        else:
            model_info = extract_model_info(product)
            width = row.get('Width', '')
            if not width or pd.isna(width):
                width = model_info.get('width', '')
            
            label_data = {
                'Sipariş No': str(row.get('Sipariş No', row.get('Id', ''))),
                'Müşteri Adı': str(row.get('Müşteri', row.get('Alıcı', ''))),
                'Genişlik': str(width) if width else '',
                'Model': model_info['model'],
                'Ölçü': str(row.get('Ring Size', '')),
                'Lazer': '✓' if pd.notna(row.get('Personalization')) else '',
                'Not': str(row.get('Kendi Notum', '')) if pd.notna(row.get('Kendi Notum')) else ''
            }
            
            # Çoklu ring size
            ring_size_str = label_data['Ölçü']
            if ',' in ring_size_str:
                ring_sizes = [s.strip() for s in ring_size_str.split(',')]
            else:
                ring_sizes = [ring_size_str]
        
        # Her ring size için etiket
        for ring_size in ring_sizes:
            col = label_count % labels_per_row
            row_num = (label_count // labels_per_row) % labels_per_column
            
            if label_count > 0 and label_count % labels_per_page == 0:
                c.showPage()
            
            x = margin_x + (col * label_width)
            y = page_height - margin_y - ((row_num + 1) * label_height)
            
            # Etiket çiz
            label_data_copy = label_data.copy()
            label_data_copy['Ölçü'] = ring_size
            draw_label(c, x, y, label_width, label_height, label_data_copy)
            
            label_count += 1
    
    c.save()
    buffer.seek(0)
    return buffer, label_count

def draw_label(c, x, y, width, height, data):
    """Tek etiket çizer"""
    # Dış çerçeve
    c.setStrokeColor(black)
    c.setLineWidth(1)
    c.rect(x, y, width, height)
    
    # İç çizgiler
    line_height = height / 7
    for i in range(1, 7):
        line_y = y + (i * line_height)
        c.setLineWidth(0.3)
        c.line(x, line_y, x + width, line_y)
    
    # Metin
    text_x = x + 0.1 * cm
    font_size = 7
    
    rows = [
        ('Sipariş No', data['Sipariş No']),
        ('Müşteri Adı', data['Müşteri Adı']),
        ('Genişlik', data['Genişlik']),
        ('Model', data['Model']),
        ('Ölçü', data['Ölçü']),
        ('Lazer', data['Lazer']),
        ('Not', data['Not'])
    ]
    
    for i, (label, value) in enumerate(rows):
        row_y = y + height - ((i + 0.65) * line_height)
        
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(text_x, row_y, label)
        
        c.setFont("Helvetica", font_size)
        value_x = x + 1.7 * cm
        
        if len(str(value)) > 18:
            value = str(value)[:15] + "..."
        
        c.drawString(value_x, row_y, str(value))

# Ana uygulama
st.markdown("### 📤 Excel Dosyası Yükle")

uploaded_file = st.file_uploader(
    "Etsy siparişlerinizi içeren Excel dosyasını seçin",
    type=['xlsx', 'xls', 'csv'],
    help="Etsy'den export ettiğiniz sipariş dosyasını yükleyin"
)

if uploaded_file:
    try:
        # Excel'i oku
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success(f"✅ {len(df)} sipariş yüklendi!")
        
        # Önizleme
        with st.expander("📋 Sipariş Önizlemesi (İlk 5 Satır)"):
            st.dataframe(df.head())
        
        # Sütun kontrolü
        st.markdown("### 🔍 Sütun Kontrolü")
        cols = st.columns(3)
        
        with cols[0]:
            st.info(f"**Sipariş No:** {'✅' if 'Sipariş No' in df.columns or 'Id' in df.columns else '❌'}")
        with cols[1]:
            st.info(f"**Müşteri:** {'✅' if 'Müşteri' in df.columns or 'Alıcı' in df.columns else '❌'}")
        with cols[2]:
            st.info(f"**Ürün:** {'✅' if 'Ürün' in df.columns else '❌'}")
        
        # PDF oluştur butonu
        st.markdown("### 🎨 PDF Oluştur")
        
        if st.button("🏷️ PDF Etiket Oluştur", type="primary"):
            with st.spinner("PDF oluşturuluyor..."):
                pdf_buffer, total_labels = create_pdf_labels(df)
                
                st.success(f"✅ {total_labels} etiket başarıyla oluşturuldu!")
                
                # İndir butonu
                st.download_button(
                    label="📥 PDF İndir",
                    data=pdf_buffer,
                    file_name=f"etiketler_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf"
                )
                
                st.balloons()
    
    except Exception as e:
        st.error(f"❌ Hata: {str(e)}")
        st.info("💡 Excel dosyanızda 'Sipariş No', 'Müşteri', 'Ürün' sütunlarının olduğundan emin olun.")

else:
    st.info("👆 Lütfen Excel dosyanızı yükleyin")

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 20px;">
    <b>🏷️ Etsy Etiket Üretici v2.0</b><br>
    3x5cm Çerçeveli PDF Etiketler<br>
    Model Çevirileri: Dome→Bombe, Flat→Düz, Bevel→Çatı
</div>
""", unsafe_allow_html=True)
