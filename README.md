# Etsy Atolye Yonetim Sistemi v2

Mevcut sistemi bozmadan yan yana calistirilacak moduler Streamlit uygulamasi.

## Kurulum

```powershell
cd C:\Users\hasan\Documents\Codex\2026-05-10\elimizde-api-var-bir-sipari-y\etsy_atolye_v2
pip install -r requirements.txt
```

## Secrets

`.streamlit/secrets.example.toml` dosyasini `.streamlit/secrets.toml` olarak kopyalayin ve degerleri doldurun.

API anahtarlari koda yazilmaz. Eski kodda gorunen anahtarlari ShipEntegra panelinden yenilemeniz onerilir.

## Calistirma

```powershell
streamlit run app.py
```

Alternatif olarak bu klasorde:

```powershell
.\run_v2.ps1
```

Varsayilan test portu: `http://localhost:8502`

## Temel duzeltmeler

- Etiketi basilan siparisler hem ShipEntegra alanlarindan hem de `BasilanEtiketler` sheet'inden filtrelenir.
- Manuel ShipEntegra gonderileri `M` ile baslayan siparisler icin son 30 gun mantigi ile yakalanir.
- Renk, genislik, model ve olcu alanlari varyasyon alias sistemiyle daha esnek okunur.
- Streamlit tablo duzenlemeleri `session_state` icinde kalici tutulur.
- Basa don / temizle butonu eklidir.
