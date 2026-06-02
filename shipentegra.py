from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

from config import SHIPENTEGRA_API_BASE, STORE_CONFIGS
from parser import api_orders_to_standard_df
from sheets import get_printed_order_ids
from utils import clean_text


def get_store_credentials(store_code: str):
    cfg = STORE_CONFIGS.get(store_code, {})
    secret_key = cfg.get("api_key_secret", "")
    try:
        key = st.secrets[secret_key]["api_key"]
        secret = st.secrets[secret_key]["api_secret"]
        return key, secret
    except Exception:
        return None, None


def get_bearer_token(client_id: str, client_secret: str) -> str | None:
    try:
        resp = requests.post(
            f"{SHIPENTEGRA_API_BASE}/auth/token",
            json={"clientId": client_id, "clientSecret": client_secret},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("data", {}).get("accessToken")
    except requests.RequestException:
        return None


def fetch_pending_orders_for_store(store_code: str) -> tuple[pd.DataFrame, list[str]]:
    warnings = []
    client_id, client_secret = get_store_credentials(store_code)
    if not client_id or not client_secret:
        return pd.DataFrame(), [f"{store_code} icin API anahtari secrets.toml icinde bulunamadi."]

    token = get_bearer_token(client_id, client_secret)
    if not token:
        return pd.DataFrame(), [f"{store_code} token alinamadi. Kimlik bilgilerini kontrol edin."]

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    all_orders = []
    page = 1

    while True:
        try:
            resp = requests.get(
                f"{SHIPENTEGRA_API_BASE}/orders",
                headers=headers,
                params={"page": page, "limit": 100},
                timeout=30,
            )
        except requests.exceptions.Timeout:
            return pd.DataFrame(), [f"{store_code}: API istegi zaman asimina ugradi."]
        except requests.RequestException as exc:
            return pd.DataFrame(), [f"{store_code}: Baglanti hatasi: {exc}"]

        if resp.status_code == 401:
            return pd.DataFrame(), [f"{store_code}: Token gecersiz (401)."]
        if resp.status_code != 200:
            return pd.DataFrame(), [f"{store_code}: API hatasi {resp.status_code}."]

        data = resp.json()
        orders = data.get("data", {}).get("orders", [])
        if not orders:
            break

        all_orders.extend(orders)
        if len(orders) < 100:
            break
        page += 1

    printed_ids = get_printed_order_ids()
    pending = []
    filtered_label = 0
    filtered_printed = 0

    for order in all_orders:
        identities = order_identities(order)
        if not is_pending_order(order):
            continue
        if has_label(order):
            filtered_label += 1
            continue
        if identities and any(identity in printed_ids for identity in identities):
            filtered_printed += 1
            continue
        pending.append(order)

    if filtered_label:
        warnings.append(f"{store_code}: {filtered_label} sipariste ShipEntegra etiketi var, cikarildi.")
    if filtered_printed:
        warnings.append(f"{store_code}: {filtered_printed} siparis BasilanEtiketler kaydinda var, cikarildi.")
    if not pending:
        return pd.DataFrame(), warnings

    return api_orders_to_standard_df(pending, store_code), warnings


def order_identity(order: dict) -> str:
    return clean_text(
        order.get("id")
        or order.get("shipentegra_id")
        or order.get("shipment_id")
        or order.get("orderId")
        or order.get("order_id")
        or order.get("marketplaceOrderId")
    )


def order_identities(order: dict) -> set[str]:
    values = [
        order.get("id"),
        order.get("shipentegra_id"),
        order.get("shipment_id"),
        order.get("orderId"),
        order.get("order_id"),
        order.get("marketplaceOrderId"),
        order.get("marketplace_order_id"),
    ]
    return {clean_text(value) for value in values if clean_text(value)}


def has_label(order: dict) -> bool:
    label_fields = [
        order.get("last_labelled"),
        order.get("my_tracking_number"),
        order.get("se_tracking_number"),
        order.get("activeLabelTrackingNumber"),
        order.get("shipentegra_label"),
    ]
    for value in label_fields:
        text = clean_text(value)
        if text and text.lower() not in {"none", "nan", "null"}:
            return True
    return False


def is_pending_order(order: dict) -> bool:
    status = clean_text(order.get("status"))
    my_status = clean_text(order.get("my_status"))
    if my_status:
        return my_status == "2"
    return status == "2"


def is_pending_or_manual(order: dict, manual_days: int = 30) -> bool:
    return is_pending_order(order)


def is_cancelled_order(order: dict) -> bool:
    cancel_words = [
        "cancel",
        "cancelled",
        "canceled",
        "iptal",
        "refunded",
        "refund",
        "closed",
        "void",
    ]
    fields = [
        "status",
        "my_status",
        "tracking_status_id",
        "my_tracking_status",
        "tags",
        "my_note",
        "customer_note",
        "order_status",
        "marketplace_status",
        "shipment_status",
    ]
    text = " ".join(clean_text(order.get(field)).lower() for field in fields)
    return any(word in text for word in cancel_words)


def is_manual_order(order: dict) -> bool:
    order_id = order_identity(order).upper()
    if order_id.startswith("M"):
        return True

    source_text = " ".join(
        clean_text(order.get(field)).lower()
        for field in [
            "source",
            "order_source",
            "marketplace",
            "marketplace_name",
            "platform",
            "integration",
            "store_type",
        ]
    )
    if "manual" in source_text or "manuel" in source_text:
        return True
    return False
