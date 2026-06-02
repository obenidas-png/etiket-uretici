# Render ile Calisanlara Acma

Bu kurulum uygulamayi tek bir linkten kullanilabilir hale getirir. Google Sheets baglantisi icin OAuth token yerine Google Service Account kullanilir; boylece token yenileme derdi olmaz.

## 1. Google Service Account Olustur

1. Google Cloud Console'da bir proje acin veya mevcut projeyi secin.
2. `APIs & Services > Library` alanindan `Google Sheets API` etkinlestirin.
3. `IAM & Admin > Service Accounts` alanindan yeni service account olusturun.
4. Service account icin JSON key indirin.
5. JSON dosyasindaki `client_email` adresini kopyalayin.
6. Siparis Google Sheet dosyasini bu `client_email` ile `Editor` olarak paylasin.

## 2. Yerel Secrets Dosyasini Hazirla

Indirdiginiz JSON dosyasini su komutla `.streamlit/secrets.toml` icine aktarabilirsiniz:

```powershell
cd "C:\Users\hasan\Documents\Codex\2026-05-10\elimizde-api-var-bir-sipari-y\etsy_atolye_v2"
& "C:\Users\hasan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" import_gcp_service_account.py "C:\path\service-account.json"
```

Sonra `.streamlit/secrets.toml` icinde ShipEntegra ve uygulama sifresi alanlarini doldurun:

```toml
[shipentegra]
api_key = "CPQ_CLIENT_ID"
api_secret = "CPQ_CLIENT_SECRET"

[shipentegra_fory]
api_key = "FRY_CLIENT_ID"
api_secret = "FRY_CLIENT_SECRET"

[shipentegra_crss]
api_key = "CRSS_CLIENT_ID"
api_secret = "CRSS_CLIENT_SECRET"

[app]
password = "calisanlara-verilecek-sifre"
```

## 3. GitHub'a Yuklenecekler

Kod dosyalarini GitHub'a yukleyin. Su dosyalar kesinlikle GitHub'a yuklenmemelidir:

- `.streamlit/secrets.toml`
- `.streamlit/oauth_token.json`
- `.streamlit/oauth_client.json`
- `service_account.json`
- `data/`
- PDF, ZIP ve CSV ciktilari

`.gitignore` bu gizli dosyalari disarida tutacak sekilde kontrol edilmelidir.

## 4. Render Web Service

Render'da `New > Web Service` secin ve GitHub reposunu baglayin.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true
```

## 5. Render Secret File

Render panelinde `Environment > Secret Files` alanindan yeni secret file ekleyin.

Path:

```text
.streamlit/secrets.toml
```

Content:

Yereldeki su dosyanin iceriginin tamamini yapistirin:

```text
etsy_atolye_v2/.streamlit/secrets.toml
```

Render icin ayrica `.streamlit/oauth_token.json` eklemeyin. Service Account yeterlidir.

## 6. Calisanlara Verilecek Bilgiler

Deploy basarili olunca Render size su tarz bir link verir:

```text
https://etsy-atolye-siparis.onrender.com
```

Calisanlara bu linki ve `[app] password` alanindaki sifreyi verin.

## 7. Notlar

- Render ucretsiz planda uygulama uykuya gecebilir; ilk acilis yavas olabilir.
- Gunluk aktif kullanim icin ucretli `Starter` plan daha stabildir.
- Google Sheet'i sadece service account e-postasi ile paylasmak yeterlidir; calisanlarin Google hesabina Sheets yetkisi vermeniz gerekmez.
