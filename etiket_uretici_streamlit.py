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
        store_name = str(row.get('MagazaAdı', ''))
        
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
        
        # MAĞAZAYA GÖRE İŞLEM
        if 'cerasus' in store_name.lower():
            # CerasusJewelry - Takı mağazası
            # Model/renk yok, sadece ürün adı ve renk var
            
            # Ürün adını sadeleştir
            product_clean = product.split(' - ')[0]  # İlk kısmı al
            if len(product_clean) > 40:
                product_clean = product_clean[:37] + "..."
            
            # Renk bilgisi - Özellikler'den veya ürün adından
            color = props.get('Metal', '')  # Önce props'tan bak
            if not color:  # Props'ta yoksa ürün adından çıkar
                product_lower = product.lower()
                if '14k yellow gold' in product_lower or 'yellow gold' in product_lower:
                    color = '14K Yellow Gold'
                elif '14k white gold' in product_lower or 'white gold' in product_lower:
                    color = '14K White Gold'
                elif '14k rose gold' in product_lower or 'rose gold' in product_lower:
                    color = '14K Rose Gold'
                elif 'sterling silver' in product_lower or 'silver' in product_lower:
                    color = 'Sterling Silver'
            
            orders.append({
                'Mağaza': store_name,
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
            # Chepniq - Alyans mağazası
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
                
                # Set of 2 ürün adından genişlik bilgilerini çıkar
                # "Hers size 6: 2mm / His size 11 1/2: 4mm" gibi
                width1 = '2MM'  # Varsayılan kadın genişliği
                width2 = '4MM'  # Varsayılan erkek genişliği
                
                # Ürün adından gerçek genişlikleri bul
                if 'hers' in product_lower and 'his' in product_lower:
                    # "Hers size 6: 2mm / His size 11: 4mm" formatı
                    hers_match = re.search(r'hers[^:]*:\s*(\d+)\s*mm', product_lower)
                    his_match = re.search(r'his[^:]*:\s*(\d+)\s*mm', product_lower)
                    if hers_match:
                        width1 = hers_match.group(1) + 'MM'
                    if his_match:
                        width2 = his_match.group(1) + 'MM'
                elif '2mm' in product_lower and '4mm' in product_lower:
                    width1 = '2MM'
                    width2 = '4MM'
                elif width:  # Props'tan gelen genişlik varsa
                    width1 = width
                    width2 = width
                
                # İki ayrı sipariş oluştur
                if size1:
                    orders.append({
                        'Mağaza': store_name,
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
                        'Mağaza': store_name,
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
                    'Mağaza': store_name,
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
    margin_x = 0.2 * cm  # 2mm kenar boşluğu
    margin_y = 0.2 * cm  # 2mm kenar boşluğu
    
    # Etiketler arası boşluk (makasla kesim için)
    gap_x = 0.15 * cm  # 1.5mm yatay boşluk
    gap_y = 0.15 * cm  # 1.5mm dikey boşluk
    
    labels_per_row = 4
    labels_per_column = 9
    labels_per_page = labels_per_row * labels_per_column
    
    label_count = 0
    
    for idx, row in orders_df.iterrows():
        col = label_count % labels_per_row
        row_num = (label_count // labels_per_row) % labels_per_column
        
        if label_count > 0 and label_count % labels_per_page == 0:
            c.showPage()
        
        # Boşluklu pozisyon hesaplama
        x = margin_x + (col * (label_width + gap_x))
        y = page_height - margin_y - ((row_num + 1) * (label_height + gap_y))
        
        # Etiket çiz
        draw_label(c, x, y, label_width, label_height, row)
        label_count += 1
    
    c.save()
    buffer.seek(0)
    return buffer

def draw_label(c, x, y, width, height, data):
    """Tek etiket çizer - Mağazaya göre farklı format - Türkçe ASCII dönüşümü"""
    
    # Türkçe karakterleri ASCII'ye çevir
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
    
    # Mağaza kontrolü
    store = str(data.get('Mağaza', '')).lower()
    
    if 'cerasus' in store:
        # CerasusJewelry için özel format
        line_height = height / 7
        for i in range(1, 7):
            line_y = y + (i * line_height)
            c.setLineWidth(0.3)
            c.line(x, line_y, x + width, line_y)
        
        # Not alanını temizle
        note = ''
        if pd.notna(data.get('Kişiselleştirme')):
            note = str(data['Kişiselleştirme'])
            note = note.replace('&quot;', '"')
            note = note.replace('&#39;', "'")
            note = note.replace('&amp;', '&')
            note = turkce_to_ascii(note[:30])
        
        rows = [
            ('Magaza', 'CerasusJewelry'),
            ('Siparis No', str(data['Sipariş No'])),
            ('Musteri', turkce_to_ascii(str(data['Müşteri'])[:20])),
            ('Urun', turkce_to_ascii(str(data['Ürün'])[:25])),
            ('Zincir', ''),
            ('Renk', turkce_to_ascii(str(data['Renk'])[:15])),
            ('Not', note)
        ]
    else:
        # Chepniq ve diğer mağazalar için standart format
        line_height = height / 7
        for i in range(1, 7):
            line_y = y + (i * line_height)
            c.setLineWidth(0.3)
            c.line(x, line_y, x + width, line_y)
        
        # Kişiselleştirme metnini temizle
        pers_text = ''
        if pd.notna(data['Kişiselleştirme']):
            pers_text = str(data['Kişiselleştirme'])
            pers_text = pers_text.replace('&quot;', '"')
            pers_text = pers_text.replace('&#39;', "'")
            pers_text = pers_text.replace('&amp;', '&')
            pers_text = pers_text[:30]
        
        customer_name = turkce_to_ascii(str(data['Müşteri'])[:25])
        store_display = turkce_to_ascii(str(data.get('Mağaza', 'CPNQ')))
        
        rows = [
            ('Magaza', store_display),
            ('Siparis No', str(data['Sipariş No'])),
            ('Musteri Adi', customer_name),
            ('Genislik', str(data['Genişlik'])),
            ('Model', turkce_to_ascii(f"{data['Model']} {data['Renk']}".strip())),
            ('Olcu', str(data['Ölçü'])),
            ('Lazer', pers_text)
        ]
    
    # Metni yaz
    for i, (label, value) in enumerate(rows):
        row_y = y + height - ((i + 0.65) * line_height)
        
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(text_x, row_y, label)
        
        c.setFont("Helvetica", font_size - 1)
        value_x = x + 1.7 * cm
        
        try:
            c.drawString(value_x, row_y, str(value))
        except:
            safe_value = turkce_to_ascii(str(value))
            c.drawString(value_x, row_y, safe_value)

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
    """Kişiselleştirme listesi TXT oluşturur - Blok format"""
    personalized = orders_df[orders_df['Kişiselleştirme'].notna()].copy()
    
    if len(personalized) == 0:
        return "Kişiselleştirme gerektiren sipariş yok."
    
    output = "Kişiselleştirme Listesi\n"
    output += "=======================\n\n"
    
    for idx, row in personalized.iterrows():
        customer = str(row['Müşteri'])
        width = str(row['Genişlik'])
        
        # Kişiselleştirme metnini temizle
        text = str(row['Kişiselleştirme'])
        # HTML entities temizle
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        text = text.replace('&amp;', '&')
        text = text.replace('\\n', '\n   ')  # Alt satıra geç ve girintili yaz
        
        # Blok formatı
        output += f"Müşteri: {customer}\n"
        output += f"Genişlik: {width}\n"
        output += f"Kişiselleştirme:\n   {text}\n"
        output += "-" * 80 + "\n\n"
    
    return output

def create_kontrol_listesi(orders_df, store_name=''):
    """Kontrol listesi TXT oluşturur - Türkçe ve özel karakter desteği"""
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
        
        # Kişiselleştirme metni temizle
        pers = ''
        if pd.notna(row['Kişiselleştirme']):
            pers = str(row['Kişiselleştirme'])
            # HTML entities temizle
            pers = pers.replace('&quot;', '"')
            pers = pers.replace('&#39;', "'")
            pers = pers.replace('&amp;', '&')
            pers = pers.replace('\\n', ' ')
            pers = pers[:100]
        
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
        # Yeni dosya yüklendiğinde eski verileri temizle
        if 'last_file_name' not in st.session_state or st.session_state.get('last_file_name') != uploaded_file.name:
            st.session_state['files_created'] = False
            st.session_state['last_file_name'] = uploaded_file.name
        
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
                
                # Session state'e kaydet
                st.session_state['pdf_ready'] = pdf_buffer.getvalue()
                st.session_state['uretim_ready'] = uretim_txt
                st.session_state['kisisel_ready'] = kisisel_txt
                st.session_state['kontrol_ready'] = kontrol_txt
                st.session_state['files_created'] = True
            
            st.success("✅ Tüm dosyalar hazır!")
            st.balloons()
        
        # Dosyalar hazırsa indirme butonlarını göster
        if st.session_state.get('files_created', False):
            st.markdown("### 📥 Dosyaları İndir")
            
            st.info("💡 **İpucu:** Tüm dosyaları indirebilirsiniz. Her birine tıkladığınızda diğerleri kaybolmayacak!")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📥 PDF Etiketler İndir",
                    data=st.session_state['pdf_ready'],
                    file_name=f"etiketler_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    key="download_pdf"
                )
                
                st.download_button(
                    label="📥 Üretim Listesi İndir",
                    data=st.session_state['uretim_ready'].encode('utf-8'),
                    file_name=f"uretim_listesi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    key="download_uretim"
                )
            
            with col2:
                st.download_button(
                    label="📥 Kişiselleştirme Listesi İndir",
                    data=st.session_state['kisisel_ready'].encode('utf-8'),
                    file_name=f"kisisellestime_listesi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    key="download_kisisel"
                )
                
                st.download_button(
                    label="📥 Kontrol Listesi İndir",
                    data=st.session_state['kontrol_ready'].encode('utf-8'),
                    file_name=f"kontrol_listesi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    key="download_kontrol"
                )
            
            # Yeni dosya yükle butonu
            st.markdown("---")
            if st.button("🔄 Yeni CSV Yükle", type="secondary"):
                st.session_state['files_created'] = False
                st.rerun()
    
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
