SHEET_URL = "https://docs.google.com/spreadsheets/d/1xD6d_drnDc9YYnzvT4XGXpuBTtAHB7x2p6Eai1bKlps/edit"

SHIPENTEGRA_API_BASE = "https://api.shipentegra.com/v1"

STORE_CONFIGS = {
    "CPQ": {
        "label": "Chepniq",
        "api_key_secret": "shipentegra",
        "color": "#1a3a5c",
    },
    "FRY": {
        "label": "Foria",
        "api_key_secret": "shipentegra_fory",
        "color": "#8b0000",
    },
    "CRSS": {
        "label": "Cerasus",
        "api_key_secret": "shipentegra_crss",
        "color": "#1a5c2a",
    },
}

SIPARIS_COLS = [
    "Sipariş No",
    "ShipEntegra ID",
    "Müşteri",
    "Mağaza",
    "Genişlik",
    "Renk",
    "Model",
    "Ölçü",
    "Kişiselleştirme",
    "Özel Not",
    "Durum",
    "Etiket",
    "Eklenme Tarihi",
]

PROBLEM_COLS = [
    "Sipariş No",
    "Müşteri",
    "Mağaza",
    "Genişlik",
    "Model",
    "Ölçü",
    "Durum",
    "Not",
    "Güncelleme Saati",
    "Ekleyen",
]
