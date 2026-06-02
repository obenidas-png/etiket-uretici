from __future__ import annotations

from pathlib import Path
import math
import json

import pandas as pd
import streamlit as st
import urllib.parse
import urllib.request
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google.oauth2.credentials import Credentials as UserCredentials
import gspread
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request

from config import PROBLEM_COLS, SHEET_URL, SIPARIS_COLS
from utils import now_tr


DATA_DIR = Path(__file__).resolve().parent / "data"
LOCAL_SIPARIS = DATA_DIR / "siparisler.csv"
LOCAL_PRINTED = DATA_DIR / "basilan_etiketler.csv"
LOCAL_PROBLEMS = DATA_DIR / "sorunlu_siparisler.csv"
OAUTH_TOKEN = Path(__file__).resolve().parent / ".streamlit" / "oauth_token.json"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
GOOGLE_AUTH_ERROR_MESSAGE = (
    "Google Sheets OAuth yetkisi gecersiz veya suresi dolmus. "
    "Yerelde `python authorize_google_oauth.py` calistirip yeni `.streamlit/oauth_token.json` olusturun; "
    "Render kullaniyorsaniz `.streamlit/secrets.toml` icindeki `gcp_service_account` ayarlarini kontrol edin. "
    "Bu oturumda veriler gecici olarak yerel CSV dosyalarina yazilacak."
)


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@st.cache_resource
def get_gsheet():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_service_account_info(creds_dict, scopes=GOOGLE_SCOPES)
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL)
    except Exception:
        pass
    oauth_ss = get_gsheet_with_oauth()
    if oauth_ss is not None:
        return oauth_ss
    return None


def get_gsheet_with_oauth():
    try:
        token_info = load_oauth_token_info()
        if token_info is None:
            return None
        creds = UserCredentials.from_authorized_user_info(token_info, GOOGLE_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        client = gspread.authorize(creds)
        return client.open_by_url(SHEET_URL)
    except RefreshError:
        return None
    except Exception:
        return None


def is_google_auth_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, RefreshError):
            return True
        if "invalid_grant" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def handle_google_auth_error(exc: Exception) -> bool:
    if not is_google_auth_error(exc):
        return False
    try:
        get_gsheet.clear()
    except Exception:
        pass
    if not st.session_state.get("_google_auth_error_shown"):
        st.warning(GOOGLE_AUTH_ERROR_MESSAGE)
        st.session_state["_google_auth_error_shown"] = True
    return True


def text_variants(text: str) -> list[str]:
    variants = [text]
    try:
        fixed = text.encode("cp1252").decode("utf-8")
        if fixed not in variants:
            variants.append(fixed)
    except UnicodeError:
        pass
    return variants


def load_oauth_token_info():
    try:
        token_secret = st.secrets.get("google_oauth_token", {})
        if token_secret:
            return dict(token_secret)
    except Exception:
        pass

    try:
        token_json = st.secrets.get("google_oauth_token_json", "")
        if token_json:
            return json.loads(token_json)
    except Exception:
        pass

    if OAUTH_TOKEN.exists():
        try:
            return json.loads(OAUTH_TOKEN.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def worksheet(title: str, headers: list[str]):
    ss = get_gsheet()
    if ss is None:
        return None
    auth_error = None
    for candidate in text_variants(title):
        try:
            return ss.worksheet(candidate)
        except Exception as exc:
            if handle_google_auth_error(exc):
                return None
            auth_error = exc
    try:
        ws = ss.add_worksheet(title=text_variants(title)[-1], rows=5000, cols=max(len(headers), 10))
        ws.append_row(headers)
        return ws
    except Exception as exc:
        if handle_google_auth_error(exc):
            return None
        return None


def load_siparis_sheet() -> pd.DataFrame:
    select_col = "Se" + chr(231)
    sheet_title = "Sipari" + chr(351) + "ler"
    columns = [select_col] + SIPARIS_COLS
    data = []
    for candidate in text_variants(sheet_title):
        ws = worksheet(candidate, columns)
        if ws is None:
            continue
        try:
            candidate_data = ws.get_all_values()
        except Exception as exc:
            if handle_google_auth_error(exc):
                return load_local_csv(LOCAL_SIPARIS, columns)
            continue
        if len(candidate_data) > 1:
            data = candidate_data
            break
        if not data:
            data = candidate_data
    if not data:
        return load_local_csv(LOCAL_SIPARIS, columns)
    if len(data) <= 1:
        return pd.DataFrame(columns=columns)
    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)
    for order_no_col in text_variants("Sipari" + chr(351) + " No"):
        if order_no_col in df.columns:
            df = df[df[order_no_col].astype(str).str.strip() != ""].reset_index(drop=True)
            break
    return df


def save_siparis_sheet(df: pd.DataFrame) -> tuple[bool, int]:
    select_col = "Se" + chr(231)
    sheet_title = "Sipari" + chr(351) + "ler"
    ws = worksheet(sheet_title, [select_col] + SIPARIS_COLS)
    if ws is None:
        return save_local_siparis(df)
    df = sanitize_df_for_sheet(df)
    rows = []
    for _, row in df.iterrows():
        rows.append(
            [
                False,
                sheet_value(row.get("Sipariş No", "")),
                sheet_value(row.get("ShipEntegra ID", "")),
                sheet_value(row.get("Müşteri", "")),
                sheet_value(row.get("Mağaza", "")),
                sheet_value(row.get("Genişlik", "")),
                sheet_value(row.get("Renk", "")),
                sheet_value(row.get("Model", "")),
                sheet_value(row.get("Ölçü", "")),
                sheet_value(row.get("Kişiselleştirme", "")),
                sheet_value(row.get("Özel Not", "")),
                sheet_value(row.get("Durum", "")),
                sheet_value(row.get("Etiket", "")),
                sheet_value(row.get("Eklenme Tarihi", "")) or now_tr(),
            ]
        )
    ws.resize(rows=max(len(rows) + 50, 200), cols=len(["Seç"] + SIPARIS_COLS))
    ws.clear()
    ws.update("A1", [["Seç"] + SIPARIS_COLS])
    if rows:
        ws.update("A2", rows, value_input_option="RAW")
    setup_siparis_validation(ws)
    return True, len(rows)


def merge_orders_into_sheet(new_df: pd.DataFrame) -> tuple[bool, int]:
    existing = load_siparis_sheet()
    if "Seç" in existing.columns:
        existing = existing.drop(columns=["Seç"])
    if existing.empty:
        merged = new_df.copy()
    else:
        merged = pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates(
            subset=["ShipEntegra ID", "Sipariş No", "Ölçü", "Genişlik", "Model"],
            keep="last",
        )
    return save_siparis_sheet(merged)


def setup_siparis_validation(ws) -> bool:
    try:
        sheet_id = ws.id
        requests = [
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 5000,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True, "strict": True},
                }
            }
        ]
        validations = [
            {"col": 3, "values": ["CPQ", "FRY", "CRSS"]},
            {"col": 4, "values": ["1MM", "2MM", "3MM", "4MM", "5MM", "6MM", "7MM", "8MM"]},
            {
                "col": 5,
                "values": [
                    "BEYAZ",
                    "MAT BEYAZ",
                    "SARI",
                    "MAT SARI",
                    "ROSE",
                    "MAT ROSE",
                    "14K Yellow Gold",
                    "14K White Gold",
                    "14K Rose Gold",
                    "Sterling Silver",
                ],
            },
            {"col": 6, "values": ["BOMBE", "ÇATI", "ÇATI MAT", "DÜZ", "TEKTAŞ", "FANTAZİ", "YENİLEME"]},
            {"col": 11, "values": ["ACİL", "10K GOLD", "14K GOLD", "18K GOLD", "DİKKAT"]},
        ]
        for item in validations:
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 5000,
                            "startColumnIndex": item["col"],
                            "endColumnIndex": item["col"] + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [{"userEnteredValue": value} for value in item["values"]],
                            },
                            "showCustomUi": True,
                            "strict": False,
                        },
                    }
                }
            )
        ws.spreadsheet.batch_update({"requests": requests})
        return True
    except Exception:
        return False


def get_printed_sheet():
    return worksheet("BasilanEtiketler", ["SiparişNo", "ShipEntegraID", "Mağaza", "Tarih"])


def save_printed_orders(order_ids: list[str], store: str, shipentegra_ids: list[str] | None = None) -> bool:
    ws = get_printed_sheet()
    shipentegra_ids = shipentegra_ids or []
    if ws is None:
        ensure_data_dir()
        existing = load_local_csv(LOCAL_PRINTED, ["SiparişNo", "ShipEntegraID", "Mağaza", "Tarih"])
        rows = printed_rows_dataframe(order_ids, shipentegra_ids, store)
        combined = pd.concat([existing, rows], ignore_index=True)
        combined["_key"] = combined.apply(lambda r: str(r.get("ShipEntegraID") or r.get("SiparişNo") or ""), axis=1)
        combined = combined.drop_duplicates(subset=["_key"], keep="last").drop(columns=["_key"])
        combined.to_csv(LOCAL_PRINTED, index=False, encoding="utf-8-sig")
        try:
            get_printed_order_ids.clear()
        except Exception:
            pass
        return True
    rows = printed_rows_dataframe(order_ids, shipentegra_ids, store).values.tolist()
    if rows:
        ws.append_rows(rows)
    try:
        get_printed_order_ids.clear()
    except Exception:
        pass
    return True


@st.cache_data(ttl=300)
def get_printed_order_ids() -> set[str]:
    ws = get_printed_sheet()
    if ws is None:
        ensure_data_dir()
        if not LOCAL_PRINTED.exists():
            return set()
        try:
            df = pd.read_csv(LOCAL_PRINTED, dtype=str).fillna("")
        except Exception:
            return set()
        ids = set()
        for col in list(df.columns[:2]):
            ids.update(str(value).strip() for value in df[col].tolist() if str(value).strip())
        return ids
    try:
        data = ws.get_all_values()
    except Exception as exc:
        if handle_google_auth_error(exc):
            return set()
        return set()
    ids = set()
    for row in data[1:]:
        if len(row) > 0 and str(row[0]).strip():
            ids.add(str(row[0]).strip())
        if len(row) > 1 and str(row[1]).strip():
            ids.add(str(row[1]).strip())
    return ids


def load_problem_sheet() -> pd.DataFrame:
    ws = worksheet("SorunluSiparisler", PROBLEM_COLS)
    if ws is None:
        return load_local_csv(LOCAL_PROBLEMS, PROBLEM_COLS)
    try:
        data = ws.get_all_records()
    except Exception as exc:
        if handle_google_auth_error(exc):
            return load_local_csv(LOCAL_PROBLEMS, PROBLEM_COLS)
        return pd.DataFrame(columns=PROBLEM_COLS)
    return pd.DataFrame(data) if data else pd.DataFrame(columns=PROBLEM_COLS)


def save_problem_order(row: dict) -> bool:
    ws = worksheet("SorunluSiparisler", PROBLEM_COLS)
    if ws is None:
        ensure_data_dir()
        df = load_local_csv(LOCAL_PROBLEMS, PROBLEM_COLS)
        row_data = {
            "Sipariş No": row.get("Sipariş No", ""),
            "Müşteri": row.get("Müşteri", ""),
            "Mağaza": row.get("Mağaza", ""),
            "Genişlik": row.get("Genişlik", ""),
            "Model": row.get("Model", ""),
            "Ölçü": row.get("Ölçü", ""),
            "Durum": row.get("Durum", ""),
            "Not": row.get("Not", ""),
            "Güncelleme Saati": now_tr(),
            "Ekleyen": row.get("Ekleyen", ""),
        }
        if not df.empty and str(row_data["Sipariş No"]).strip():
            mask = df["Sipariş No"].astype(str) == str(row_data["Sipariş No"])
            if mask.any():
                for col, value in row_data.items():
                    df.loc[mask, col] = value
            else:
                df = pd.concat([df, pd.DataFrame([row_data])], ignore_index=True)
        else:
            df = pd.concat([df, pd.DataFrame([row_data])], ignore_index=True)
        df.to_csv(LOCAL_PROBLEMS, index=False, encoding="utf-8-sig")
        telegram_notify(
            f"🚨 <b>Sorunlu Sipariş</b>\n"
            f"📦 #{row.get('Sipariş No', '')} [{row.get('Mağaza', '')}]\n"
            f"👤 {row.get('Müşteri', '')}\n"
            f"⚠️ {row.get('Not', '')}\n"
            f"📊 {row.get('Durum', '')}\n"
            f"✏️ {row.get('Ekleyen', '')} · {now_tr()}"
        )
        return True
    row_data = [
        row.get("Sipariş No", ""),
        row.get("Müşteri", ""),
        row.get("Mağaza", ""),
        row.get("Genişlik", ""),
        row.get("Model", ""),
        row.get("Ölçü", ""),
        row.get("Durum", ""),
        row.get("Not", ""),
        now_tr(),
        row.get("Ekleyen", ""),
    ]
    try:
        cell = ws.find(str(row.get("Sipariş No", "")))
        for idx, value in enumerate(row_data, start=1):
            ws.update_cell(cell.row, idx, value)
    except Exception:
        ws.append_row(row_data)
    telegram_notify(
        f"🚨 <b>Sorunlu Sipariş</b>\n"
        f"📦 #{row.get('Sipariş No', '')} [{row.get('Mağaza', '')}]\n"
        f"👤 {row.get('Müşteri', '')}\n"
        f"⚠️ {row.get('Not', '')}\n"
        f"📊 {row.get('Durum', '')}\n"
        f"✏️ {row.get('Ekleyen', '')} · {now_tr()}"
    )
    return True


def telegram_notify(message: str):
    try:
        token = st.secrets["telegram"]["token"]
        chat_id = st.secrets["telegram"]["chat_id"]
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = f"chat_id={chat_id}&text={urllib.parse.quote(message)}&parse_mode=HTML"
        req = urllib.request.Request(url, data=data.encode(), method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def load_local_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    ensure_data_dir()
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        return df[columns]
    except Exception:
        return pd.DataFrame(columns=columns)


def save_local_siparis(df: pd.DataFrame) -> tuple[bool, int]:
    ensure_data_dir()
    df = sanitize_df_for_sheet(df)
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "Seç": False,
                "Sipariş No": row.get("Sipariş No", ""),
                "ShipEntegra ID": row.get("ShipEntegra ID", ""),
                "Müşteri": row.get("Müşteri", ""),
                "Mağaza": row.get("Mağaza", ""),
                "Genişlik": row.get("Genişlik", ""),
                "Renk": row.get("Renk", ""),
                "Model": row.get("Model", ""),
                "Ölçü": row.get("Ölçü", ""),
                "Kişiselleştirme": row.get("Kişiselleştirme", ""),
                "Özel Not": row.get("Özel Not", ""),
                "Durum": row.get("Durum", ""),
                "Etiket": row.get("Etiket", ""),
                "Eklenme Tarihi": row.get("Eklenme Tarihi", "") or now_tr(),
            }
        )
    out = pd.DataFrame(rows, columns=["Seç"] + SIPARIS_COLS)
    out.to_csv(LOCAL_SIPARIS, index=False, encoding="utf-8-sig")
    return True, len(out)


def printed_rows_dataframe(order_ids: list[str], shipentegra_ids: list[str], store: str) -> pd.DataFrame:
    max_len = max(len(order_ids), len(shipentegra_ids), 0)
    rows = []
    for idx in range(max_len):
        order_id = str(order_ids[idx]).strip() if idx < len(order_ids) else ""
        se_id = str(shipentegra_ids[idx]).strip() if idx < len(shipentegra_ids) else ""
        if order_id or se_id:
            rows.append([order_id, se_id, store, now_tr()])
    return pd.DataFrame(rows, columns=["SiparişNo", "ShipEntegraID", "Mağaza", "Tarih"])


def sanitize_df_for_sheet(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy() if df is not None else pd.DataFrame()
    df = df.replace([float("inf"), float("-inf")], "")
    df = df.fillna("")
    return df


def sheet_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value)
    return "" if text.lower() in {"nan", "none", "null", "<na>"} else text
