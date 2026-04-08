# 🔄 STREAMLIT UYGULAMASINI GÜNCELLEME

## En Kolay Yöntem: GitHub Üzerinden (5 Dakika)

---

## ADIM 1: GitHub'a Girin

1. **GitHub.com**'a gidin
2. Giriş yapın
3. **Repositories** → Streamlit uygulamanızın reposunu bulun

---

## ADIM 2: Eski Dosyayı Silin

1. Repo içinde `streamlit_app.py` dosyasını bulun
2. Dosyaya tıklayın
3. Sağ üstte **çöp kutusu** ikonu → **Delete file**
4. **Commit changes** (yeşil buton)

---

## ADIM 3: Yeni Dosyayı Yükleyin

1. Repo ana sayfasına dönün
2. **Add file** → **Upload files**
3. İndirdiğiniz **yeni** `streamlit_app.py` dosyasını sürükleyin
4. **Commit changes**

---

## ADIM 4: requirements.txt Ekleyin

Repoda `requirements.txt` dosyası **YOKSA** oluşturun:

1. **Add file** → **Create new file**
2. Dosya adı: `requirements.txt`
3. İçerik:

```
pandas
openpyxl
reportlab
streamlit
```

4. **Commit changes**

---

## ADIM 5: Bekleyin (2-5 Dakika)

1. https://share.streamlit.io/ → Giriş yapın
2. Uygulamanızı bulun
3. Status: **"Deploying..."** görünecek
4. 2-5 dakika bekleyin
5. Status: **"Running"** ✅

**Güncelleme tamamlandı!** 🎉

---

## ⚠️ SORUN ÇIKARSA

### Hata Loglarını Görün:
1. https://share.streamlit.io/
2. Uygulamanızı bulun
3. **Manage app** → **Logs**
4. Hata mesajını okuyun

### Yaygın Hatalar:
- **"Module not found"** → `requirements.txt` dosyasına ekleyin
- **Deploy olmuyor** → 5-10 dakika daha bekleyin
- **Sayfa açılmıyor** → Tarayıcı cache'i temizleyin (Ctrl+F5)

---

## 📦 HAZIR DOSYALAR

İndirmeniz gerekenler:
- ✅ `streamlit_app.py` (hazırladım)
- ✅ `requirements.txt` (yukarıdaki içeriği kopyalayın)

**İşte bu kadar!** 🚀
