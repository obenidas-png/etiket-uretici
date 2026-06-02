from __future__ import annotations

import pandas as pd
import streamlit as st

from config import SHEET_URL, SIPARIS_COLS, STORE_CONFIGS
from outputs import build_files
from parser import load_file, parse_orders
from sheets import (
    load_problem_sheet,
    load_siparis_sheet,
    merge_orders_into_sheet,
    save_printed_orders,
    save_problem_order,
    save_siparis_sheet,
)
from shipentegra import fetch_pending_orders_for_store
from utils import clean_text, now_tr


st.set_page_config(page_title="Sipariş Takip Sistemi v2", page_icon="🏭", layout="wide")


CSS = """
<style>
    .main-title {
        text-align: center;
        padding: 18px;
        background: linear-gradient(135deg, #335c81 0%, #7b4f82 100%);
        border-radius: 8px;
        color: white;
        margin-bottom: 24px;
    }
    .stButton>button { width: 100%; font-weight: 700; }
    [data-testid="stFileUploader"] {
        background-color: #fff7ed;
        border: 2px dashed #f59e0b;
        border-radius: 8px;
        padding: 16px;
    }
    div[data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 10px;
        border-radius: 8px;
    }
</style>
"""


def main():
    st.markdown(CSS, unsafe_allow_html=True)
    if not check_app_password():
        return
    st.markdown('<h1 class="main-title">🏭 Sipariş Takip Sistemi v2</h1>', unsafe_allow_html=True)

    tab_orders, tab_problem = st.tabs(["📦 Siparişler ve Çıktılar", "🚨 Sorunlu Siparişler"])
    with tab_orders:
        render_orders_tab()
    with tab_problem:
        render_problem_tab()

    st.markdown("---")
    st.caption("Sipariş Takip Sistemi v2 | Modüler API, parser, Sheets ve çıktı üretimi")


def check_app_password() -> bool:
    try:
        password = st.secrets.get("app", {}).get("password", "")
    except Exception:
        password = ""
    if not password:
        return True
    if st.session_state.get("authenticated"):
        return True

    st.title("Sipariş Takip Sistemi")
    entered = st.text_input("Şifre", type="password")
    if st.button("Giriş"):
        if entered == password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Şifre hatalı.")
    return False


def render_orders_tab():
    left, right = st.columns([3, 1])

    with right:
        st.markdown("### Durum")
        current = get_current_orders()
        st.metric("Tablodaki Satır", len(current))
        st.metric("Kişiselleştirme", count_nonempty(current, "Kişiselleştirme"))
        st.metric("Eksik Bilgi", count_missing_core(current))
        st.link_button("📊 Google Sheets'i Aç", SHEET_URL, use_container_width=True)
        if st.button("🧹 Başa Dön / Ekranı Temizle", use_container_width=True):
            clear_work_state()
            st.rerun()

    with left:
        st.markdown("### 1. Sipariş Kaynağı")
        render_source_buttons()

        current = get_current_orders()
        if current.empty:
            st.info("Önce API, Google Sheets veya Excel/CSV ile sipariş yükleyin.")
            return

        st.markdown("### 2. Düzenle")
        st.caption("Değişiklikler sayfa yenilense bile bu oturumda korunur. Kalıcı yapmak için Sheets'e kaydedin.")
        edited = render_editor(current)
        set_current_orders(edited)

        st.markdown("### 3. Kaydet ve Çıktı Al")
        render_actions(edited)


def render_source_buttons():
    api_cols = st.columns(3)
    for idx, store_code in enumerate(["CPQ", "FRY", "CRSS"]):
        cfg = STORE_CONFIGS[store_code]
        with api_cols[idx]:
            if st.button(f"{cfg['label']} Siparişlerini Getir", key=f"fetch_{store_code}", type="primary"):
                with st.spinner(f"{store_code} API'den çekiliyor..."):
                    standard_df, warnings = fetch_pending_orders_for_store(store_code)
                for warning in warnings:
                    st.warning(warning)
                if standard_df.empty:
                    st.info(f"{store_code}: Çekilecek bekleyen sipariş bulunamadı.")
                    return
                parsed = parse_orders(standard_df)
                append_current_orders(parsed)
                st.success(f"{store_code}: {len(parsed)} satır eklendi.")
                st.rerun()

    st.markdown("---")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("📥 Siparişler Sheet'ini Yükle", use_container_width=True):
            with st.spinner("Google Sheets okunuyor..."):
                df = load_siparis_sheet()
            if "Seç" in df.columns:
                df = df.drop(columns=["Seç"])
            if df.empty:
                st.warning("Sheets'te sipariş bulunamadı.")
            else:
                set_current_orders(ensure_order_columns(df))
                st.success(f"{len(df)} satır yüklendi.")
                st.rerun()
    with c2:
        uploaded = st.file_uploader("Excel / CSV yükle", type=["csv", "xlsx", "xlsm"])
        if uploaded is not None:
            with st.spinner("Dosya okunuyor ve standart siparişe çevriliyor..."):
                raw_df, file_type = load_file(uploaded)
                parsed = parse_orders(raw_df)
            if parsed.empty:
                st.warning("Dosyada işlenecek sipariş bulunamadı.")
            else:
                set_current_orders(parsed)
                st.success(f"{len(parsed)} satır yüklendi ({file_type.upper()}).")
                st.rerun()


def render_editor(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_order_columns(df).reset_index(drop=True)
    display = scrub_dataframe(df.copy())
    if "Seç" not in display.columns:
        select_all = st.checkbox("Tüm satırları seç", key="select_all_rows")
        display.insert(0, "Seç", select_all)
    if "⚡" not in display.columns:
        display.insert(1, "⚡", display.apply(row_icon, axis=1))

    column_order = [
        "Seç",
        "⚡",
        "Sipariş No",
        "Müşteri",
        "Mağaza",
        "Model",
        "Renk",
        "Genişlik",
        "Ölçü",
        "Kişiselleştirme",
        "Özel Not",
        "Durum",
        "Etiket",
        "Eklenme Tarihi",
        "Ürün",
        "ShipEntegra ID",
        "Çoklu",
    ]
    display = display[unique_existing_columns(column_order, display.columns)]
    edited = st.data_editor(
        display,
        key="orders_editor",
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Seç": st.column_config.CheckboxColumn("✓", width="small"),
            "⚡": st.column_config.TextColumn("", width="small", disabled=True),
            "Mağaza": st.column_config.SelectboxColumn("Mağaza", options=["CPQ", "FRY", "CRSS", ""], width="small"),
            "Model": st.column_config.SelectboxColumn(
                "Model", options=["", "BOMBE", "ÇATI", "ÇATI MAT", "DÜZ", "TEKTAŞ", "FANTAZİ", "YENİLEME"]
            ),
            "Renk": st.column_config.SelectboxColumn(
                "Renk",
                options=[
                    "",
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
            ),
            "Genişlik": st.column_config.SelectboxColumn(
                "Gen.", options=["", "1MM", "2MM", "3MM", "4MM", "5MM", "6MM", "7MM", "8MM"], width="small"
            ),
            "Durum": st.column_config.SelectboxColumn(
                "Durum",
                options=["", "ACİL", "10K GOLD", "14K GOLD", "18K GOLD", "DİKKAT"],
                width="small",
            ),
            "Çoklu": st.column_config.CheckboxColumn("Çoklu", disabled=True),
        },
    )
    st.session_state["selected_rows"] = edited.index[edited.get("Seç", False) == True].tolist()
    clean = scrub_dataframe(edited.drop(columns=["Seç", "⚡"], errors="ignore"))
    clean = ensure_order_columns(clean)
    return clean


def render_actions(df: pd.DataFrame):
    selected = st.session_state.get("selected_rows", [])
    selected_df = df.iloc[selected].copy() if selected else pd.DataFrame()

    a, b, c, d = st.columns(4)
    with a:
        if st.button("💾 Sheets'e Kaydet", type="primary"):
            ok, count = save_siparis_sheet(df)
            if ok:
                st.success(f"{count} satır Sheets'e kaydedildi.")
            else:
                st.error("Sheets'e kaydedilemedi.")
    with b:
        if st.button("➕ Sheets'e Birleştir"):
            ok, count = merge_orders_into_sheet(df)
            if ok:
                st.success(f"Sheets güncellendi: {count} satır.")
            else:
                st.error("Sheets'e bağlanılamadı.")
    with c:
        if st.button(f"📄 Seçili Çıktı ({len(selected)})", disabled=selected_df.empty):
            st.session_state["files_selected"] = build_files(selected_df)
            st.session_state["files_selected_df"] = selected_df.copy()
    with d:
        if st.button("🚀 Tüm Liste Çıktı"):
            st.session_state["files_all"] = build_files(df)
            st.session_state["files_all_df"] = df.copy()

    if "files_selected" in st.session_state:
        render_downloads(st.session_state["files_selected"], "Seçili satırlar", "selected")
        if st.button("✅ Seçili Satırları Basıldı Olarak Kaydet", key="mark_selected_printed"):
            mark_printed(st.session_state.get("files_selected_df", selected_df))
            st.success("Seçili satırlar basıldı listesine kaydedildi.")
    if "files_all" in st.session_state:
        render_downloads(st.session_state["files_all"], "Tüm liste", "all")
        if st.button("✅ Tüm Listeyi Basıldı Olarak Kaydet", key="mark_all_printed"):
            mark_printed(st.session_state.get("files_all_df", df))
            st.success("Tüm liste basıldı listesine kaydedildi.")


def render_downloads(files: dict, title: str, key: str):
    st.markdown(f"#### {title}")
    prefix = files["prefix"]
    st.download_button(
        "📦 Tüm Dosyalar (.zip)",
        files["zip"],
        file_name=f"{prefix}-tum_dosyalar.zip",
        mime="application/zip",
        key=f"zip_{key}",
        type="primary",
        use_container_width=True,
    )
    cols = st.columns(5 if files.get("lazer_pdf") else 4)
    with cols[0]:
        st.download_button("📄 Kargo Etiketleri", files["kargo_pdf"], f"{prefix}-kargo_etiketleri.pdf", "application/pdf")
    col_idx = 1
    if files.get("lazer_pdf"):
        with cols[1]:
            st.download_button("🟠 Lazer Etiketleri", files["lazer_pdf"], f"{prefix}-lazer_etiketleri.pdf", "application/pdf")
        col_idx = 2
    with cols[col_idx]:
        st.download_button("📝 Üretim", files["uretim_txt"], f"{prefix}-uretim_listesi.txt", "text/plain")
    with cols[col_idx + 1]:
        st.download_button("✍️ Kişiselleştirme", files["kisisel_txt"], f"{prefix}-kisisellestirme.txt", "text/plain")
    with cols[col_idx + 2]:
        st.download_button("📋 Kontrol", files["kontrol_pdf"], f"{prefix}-kontrol_listesi.pdf", "application/pdf")


def render_problem_tab():
    st.markdown("### Sorunlu Sipariş Takibi")
    with st.expander("➕ Sorunlu sipariş ekle", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            order_no = st.text_input("Sipariş No")
            customer = st.text_input("Müşteri")
            store = st.selectbox("Mağaza", ["CPQ", "FRY", "CRSS", "Diğer"])
        with c2:
            width = st.text_input("Genişlik")
            model = st.text_input("Model")
            size = st.text_input("Ölçü")
        with c3:
            status = st.selectbox("Durum", ["⏳ Bekliyor", "🔄 İşlemde", "✅ Çözüldü"])
            user = st.selectbox("Düzenleyen", ["SY", "CK", "GD", "HY"])
            note = st.text_area("Not")
        if st.button("Kaydet", type="primary"):
            ok = save_problem_order(
                {
                    "Sipariş No": order_no,
                    "Müşteri": customer,
                    "Mağaza": store,
                    "Genişlik": width,
                    "Model": model,
                    "Ölçü": size,
                    "Durum": status,
                    "Not": note,
                    "Ekleyen": user,
                }
            )
            if ok:
                st.success("Kaydedildi.")
            else:
                st.error("Kaydedilemedi.")

    df = load_problem_sheet()
    if df.empty:
        st.info("Sorunlu sipariş kaydı yok.")
        return
    c1, c2 = st.columns(2)
    with c1:
        status_filter = st.selectbox("Durum filtresi", ["Tümü", "⏳ Bekliyor", "🔄 İşlemde", "✅ Çözüldü"])
    with c2:
        store_filter = st.selectbox("Mağaza filtresi", ["Tümü", "CPQ", "FRY", "CRSS"])
    if status_filter != "Tümü":
        df = df[df["Durum"].astype(str) == status_filter]
    if store_filter != "Tümü":
        df = df[df["Mağaza"].astype(str) == store_filter]
    st.dataframe(df, use_container_width=True, hide_index=True)


def get_current_orders() -> pd.DataFrame:
    return st.session_state.get("orders_df", pd.DataFrame())


def set_current_orders(df: pd.DataFrame):
    st.session_state["orders_df"] = ensure_order_columns(df).reset_index(drop=True)


def append_current_orders(df: pd.DataFrame):
    current = get_current_orders()
    combined = pd.concat([current, df], ignore_index=True) if not current.empty else df.copy()
    combined = combined.drop_duplicates(
        subset=["ShipEntegra ID", "Sipariş No", "Ölçü", "Genişlik", "Model"],
        keep="last",
    )
    set_current_orders(combined)


def ensure_order_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy() if df is not None else pd.DataFrame()
    for col in SIPARIS_COLS:
        if col not in df.columns:
            df[col] = ""
    if "Ürün" not in df.columns:
        df["Ürün"] = ""
    if "Çoklu" not in df.columns:
        duplicated = df["Sipariş No"].duplicated(keep=False) if "Sipariş No" in df.columns else False
        df["Çoklu"] = duplicated
    if "Eklenme Tarihi" in df.columns:
        df["Eklenme Tarihi"] = df["Eklenme Tarihi"].apply(lambda x: x or now_tr())
    text_cols = [col for col in df.columns if col != "Çoklu"]
    for col in text_cols:
        df[col] = df[col].apply(clean_cell)
    df = scrub_dataframe(df)
    return df


def row_icon(row) -> str:
    if "GEÇİLDİ" in clean_text(row.get("Durum")).upper():
        return "✅"
    if clean_text(row.get("Model")).upper() == "YENİLEME":
        return "♻"
    if str(row.get("Çoklu", "")).upper() in {"TRUE", "1", "DOĞRU"}:
        return "👥"
    missing = any(not clean_text(row.get(col)) for col in ["Renk", "Model", "Genişlik"] if row.get("Mağaza") != "CRSS")
    return "⚠️" if missing else ""


def count_nonempty(df: pd.DataFrame, col: str) -> int:
    if df.empty or col not in df.columns:
        return 0
    return int(df[col].fillna("").astype(str).str.strip().replace("nan", "").ne("").sum())


def count_missing_core(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    count = 0
    for _, row in df.iterrows():
        if row.get("Mağaza") == "CRSS" or clean_text(row.get("Model")).upper() == "YENİLEME":
            continue
        if any(not clean_text(row.get(col)) for col in ["Renk", "Model", "Genişlik"]):
            count += 1
    return count


def clean_cell(value):
    text = clean_text(value)
    return "" if text.lower() in {"none", "nan", "null"} else text


def scrub_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if col == "Çoklu":
            continue
        df[col] = df[col].replace({None: "", "None": "", "none": "", "nan": "", "NaN": "", "NULL": "", "null": ""})
        df[col] = df[col].fillna("")
        if df[col].dtype == object:
            df[col] = df[col].astype(str).replace(
                {
                    "None": "",
                    "none": "",
                    "nan": "",
                    "NaN": "",
                    "NULL": "",
                    "null": "",
                    "<NA>": "",
                }
            )
    return df


def unique_existing_columns(preferred_order: list[str], existing_columns) -> list[str]:
    existing = set(existing_columns)
    result = []
    seen = set()
    for col in preferred_order:
        if col in existing and col not in seen:
            result.append(col)
            seen.add(col)
    for col in existing_columns:
        if col not in seen:
            result.append(col)
            seen.add(col)
    return result


def mark_printed(df: pd.DataFrame):
    pairs = []
    seen = set()
    for _, row in df.iterrows():
        order_id = clean_text(row.get("Sipariş No"))
        se_id = clean_text(row.get("ShipEntegra ID"))
        key = se_id or order_id
        if key and key not in seen:
            pairs.append((order_id, se_id))
            seen.add(key)
    order_ids = [order_id for order_id, _ in pairs]
    shipentegra_ids = [se_id for _, se_id in pairs]
    stores = "-".join(sorted({clean_text(v) for v in df.get("Mağaza", pd.Series(dtype=str)) if clean_text(v)}))
    if order_ids or shipentegra_ids:
        save_printed_orders(order_ids, stores, shipentegra_ids)


def clear_work_state():
    for key in list(st.session_state.keys()):
        if key.startswith("files_") or key in {"orders_df", "orders_editor", "selected_rows"}:
            del st.session_state[key]


if __name__ == "__main__":
    main()
