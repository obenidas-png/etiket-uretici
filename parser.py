from __future__ import annotations

import re

import pandas as pd

from utils import clean_text, norm_key, normalize_color, normalize_width, pick_prop


WIDTH_KEYS = [
    "Width",
    "Band Width",
    "Ring Width",
    "Ring width",
    "Width of ring",
    "Genişlik",
    "Genislik",
]

COLOR_KEYS = [
    "Color",
    "Band color",
    "Metal",
    "Material",
    "General material",
    "Finish",
    "Renk",
]

SIZE_KEYS = [
    "Ring size",
    "Ring Size",
    "Size",
    "Size for You",
    "Necklace Lenght",
    "Necklace Length",
    "Chain Length",
    "Ölçü",
    "Olcu",
]

PERSONALIZATION_KEYS = [
    "Personalization",
    "Personalisation",
    "Engraving",
    "Lazer",
    "Kişiselleştirme",
    "Kisisellestirme",
]


def get_store_code(store_name) -> str:
    store_lower = clean_text(store_name).lower()
    if "foria" in store_lower or store_lower == "fry":
        return "FRY"
    if "chepniq" in store_lower or store_lower == "cpq":
        return "CPQ"
    if "cerasus" in store_lower or store_lower == "crss":
        return "CRSS"
    return clean_text(store_name)[:4].upper()


def flatten_variations(raw) -> list[dict]:
    if raw in (None, "", []):
        return []
    if isinstance(raw, dict):
        return [{clean_text(k): clean_text(v) for k, v in raw.items()}]
    if isinstance(raw, str):
        return _parse_variation_string(raw)
    if not isinstance(raw, list):
        return []

    groups = []
    for item in raw:
        if isinstance(item, list):
            group = {}
            for v in item:
                if isinstance(v, dict):
                    name = v.get("name") or v.get("property_name") or v.get("formatted_name")
                    value = v.get("value") or v.get("property_value") or v.get("formatted_value")
                    if name and value is not None:
                        group[clean_text(name)] = clean_text(value)
            if group:
                groups.append(group)
        elif isinstance(item, dict):
            if "name" in item and "value" in item:
                groups.append({clean_text(item["name"]): clean_text(item["value"])})
            else:
                groups.append({clean_text(k): clean_text(v) for k, v in item.items()})
    return groups


def _parse_variation_string(text: str) -> list[dict]:
    text = clean_text(text)
    if not text:
        return []
    props = {}
    matches = re.findall(r"Ad:([^,]+),Değer:(.*?)(?=,Ad:|$)", text)
    for key, value in matches:
        props[clean_text(key)] = clean_text(value)
    if props:
        return [props]
    for chunk in re.split(r"[;\n|]", text):
        if ":" in chunk:
            key, value = chunk.split(":", 1)
            props[clean_text(key)] = clean_text(value)
    return [props] if props else []


def xlsx_to_standard_df(df_xlsx: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df_xlsx.iterrows():
        parts = []
        for i in range(1, 8):
            name = row.get(f"Options Name {i}")
            value = row.get(f"Options Value {i}")
            if pd.notna(name) and pd.notna(value):
                parts.append(f"Ad:{name},Değer:{value}")
        rows.append(
            {
                "MagazaAdı": row.get("Market - Store Name", ""),
                "SiparişNumarası": row.get("Order - Number", ""),
                "Alıcı": row.get("Ship To - Name", ""),
                "ÜrünAdı": row.get("Item - Name", ""),
                "Özellikler": ",".join(parts) if parts else "",
                "_BuyerNote": row.get("Notes - From Buyer", ""),
                "_GiftMessage": row.get("Gift - Message", ""),
                "_ShipBy": row.get("Date - Ship By Date", ""),
                "_OrderTotal": row.get("Amount - Order Total", ""),
                "_MyNote": row.get("Private Notes", ""),
                "_Tags": "",
                "_Label": "",
            }
        )
    return pd.DataFrame(rows)


def load_file(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith((".xlsx", ".xlsm")):
        raw = pd.read_excel(uploaded_file, engine="openpyxl")
        return xlsx_to_standard_df(raw), "xlsx"
    return pd.read_csv(uploaded_file), "csv"


def api_orders_to_standard_df(orders: list[dict], store_code: str) -> pd.DataFrame:
    label_map = {"CPQ": "Chepniq", "FRY": "Foria", "CRSS": "Cerasus"}
    rows = []
    for order in orders:
        product = clean_text(order.get("name") or order.get("title") or order.get("product_name"))
        qty = _safe_int(order.get("count") or order.get("quantity") or 1, 1)
        groups = flatten_variations(order.get("variations") or order.get("variation") or order.get("options"))
        if not groups:
            groups = [{}]

        row_count = qty if len(groups) >= qty and qty > 1 else 1
        for i in range(row_count):
            props = groups[i] if i < len(groups) else _merge_props(groups)
            rows.append(
                {
                    "MagazaAdı": label_map.get(store_code, store_code),
                    "SiparişNumarası": clean_text(
                        order.get("marketplaceOrderId")
                        or order.get("marketplace_order_id")
                        or order.get("order_id")
                        or order.get("orderId")
                    ),
                    "_ShipEntegraId": clean_text(
                        order.get("id")
                        or order.get("shipentegra_id")
                        or order.get("shipment_id")
                        or order.get("orderId")
                        or order.get("order_id")
                    ),
                    "Alıcı": clean_text(order.get("ship_to_name") or order.get("buyer_name") or order.get("customer")),
                    "ÜrünAdı": product,
                    "Özellikler": _props_to_string(props),
                    "_BuyerNote": clean_text(order.get("customer_note")),
                    "_GiftMessage": clean_text(order.get("gift_message")),
                    "_ShipBy": clean_text(order.get("ship_by_date")),
                    "_OrderTotal": order.get("total_price") or 0,
                    "_MyNote": clean_text(order.get("my_note")),
                    "_Tags": clean_text(order.get("tags")),
                    "_Label": clean_text(
                        order.get("my_tracking_number")
                        or order.get("se_tracking_number")
                        or order.get("activeLabelTrackingNumber")
                        or order.get("se_label_no")
                        or order.get("se_label_number")
                        or order.get("seLabelNo")
                        or order.get("seLabelNumber")
                        or order.get("SE Etiket No")
                        or order.get("Se Etiket No")
                        or order.get("se_etiket_no")
                        or order.get("etiket_no")
                        or order.get("label_number")
                        or order.get("labelNumber")
                    ),
                }
            )
    return pd.DataFrame(rows)


def parse_orders(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    orders = []
    for _, row in df.iterrows():
        product = clean_text(row.get("ÜrünAdı"))
        product_lower = product.lower()
        if _is_fee_line(product_lower):
            continue

        store_code = get_store_code(row.get("MagazaAdı"))
        props = _extract_props(row)
        personalization = pick_prop(props, PERSONALIZATION_KEYS) or clean_text(row.get("_BuyerNote"))
        private_note = "" if clean_text(row.get("_Tags")) == "1" else clean_text(row.get("_MyNote"))
        status_note = clean_text(row.get("_Tags"))
        if status_note in {"None", "nan"}:
            status_note = ""

        if store_code == "CRSS":
            orders.append(_build_crss_order(row, props, product, personalization, private_note, status_note))
            continue

        pair_rows = _build_pair_orders(row, props, product, personalization, private_note, status_note)
        if pair_rows:
            orders.extend(pair_rows)
        else:
            orders.append(_build_standard_order(row, props, product, personalization, private_note, status_note))

    result = pd.DataFrame(orders)
    if result.empty:
        return result
    duplicated = result["Sipariş No"].duplicated(keep=False)
    result["Çoklu"] = duplicated
    return result


def _extract_props(row) -> dict:
    props = {}
    for group in flatten_variations(row.get("Özellikler")):
        props.update(group)
    return props


def _build_standard_order(row, props, product, personalization, private_note, status_note) -> dict:
    model = _detect_model(product)
    width = normalize_width(pick_prop(props, WIDTH_KEYS) or _width_from_product(product))
    color = _normalize_store_color(get_store_code(row.get("MagazaAdı")), pick_prop(props, COLOR_KEYS), product)
    size = pick_prop(props, SIZE_KEYS)
    return _base_order(row, width, color, model, size, personalization, private_note, status_note, product)


def _build_pair_orders(row, props, product, personalization, private_note, status_note) -> list[dict]:
    product_lower = product.lower()
    if not _looks_like_pair_order(product_lower, props, personalization):
        return []

    color = _normalize_store_color(get_store_code(row.get("MagazaAdı")), pick_prop(props, COLOR_KEYS), product)
    model = _detect_model(product)
    size1, size2 = _pair_sizes(props, personalization)
    width1, width2 = _pair_widths(props, personalization, product)

    rows = []
    if size1:
        rows.append(_base_order(row, width1, color, model, size1, personalization, private_note, status_note, product))
    if size2:
        rows.append(_base_order(row, width2, color, model, size2, personalization, private_note, status_note, product))
    return rows


def _build_crss_order(row, props, product, personalization, private_note, status_note) -> dict:
    product_clean = clean_crss_product(product.split(" - ")[0])
    color = _normalize_store_color("CRSS", pick_prop(props, COLOR_KEYS), product)
    size = pick_prop(props, SIZE_KEYS)
    order = _base_order(row, "", color, product_clean, size, personalization, private_note, status_note, product_clean)
    order["Model"] = product_clean
    order["Ürün"] = product_clean
    return order


def _base_order(row, width, color, model, size, personalization, private_note, status_note, product) -> dict:
    return {
        "Mağaza": get_store_code(row.get("MagazaAdı")),
        "Sipariş No": clean_text(row.get("SiparişNumarası")),
        "ShipEntegra ID": clean_text(row.get("_ShipEntegraId")),
        "Müşteri": clean_text(row.get("Alıcı")),
        "Genişlik": width,
        "Renk": color,
        "Model": clean_text(model).upper() if get_store_code(row.get("MagazaAdı")) != "CRSS" else clean_text(model),
        "Ölçü": clean_text(size),
        "Kişiselleştirme": clean_text(personalization),
        "Özel Not": clean_text(private_note),
        "Durum": clean_text(status_note),
        "Etiket": clean_text(row.get("_Label")),
        "Ürün": clean_text(product),
    }


def _detect_model(product: str) -> str:
    text = product.lower()
    if any(k in text for k in ["resizing", "size adjustment", "replacement", "renewal"]):
        return "YENİLEME"
    if "bevel" in text:
        return "ÇATI MAT" if "mat" in text else "ÇATI"
    if "dome" in text or "domed" in text:
        return "BOMBE"
    if "flat" in text or "classic" in text:
        return "DÜZ"
    if "oval" in text or "solitaire" in text:
        return "TEKTAŞ"
    return ""


def _normalize_store_color(store_code: str, color: str, product: str) -> str:
    normalized = normalize_color(color, product)
    if store_code == "CRSS":
        return normalized
    text = f"{color} {product} {normalized}".lower()
    ascii_text = text.replace("ı", "i")
    if "yellow" in text or "sari" in ascii_text or "14k yellow" in text:
        return "MAT SARI" if "mat" in text else "SARI"
    if "white" in text or "beyaz" in text or "silver" in text or "14k white" in text:
        return "MAT BEYAZ" if "mat" in text else "BEYAZ"
    if "rose" in text or "pembe" in text or "14k rose" in text:
        return "MAT ROSE" if "mat" in text else "ROSE"
    return normalized


def _width_from_product(product: str) -> str:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", product, re.I)
    return f"{match.group(1)}MM" if match else ""


def _looks_like_pair_order(product_lower: str, props: dict, personalization: str) -> bool:
    if any(token in product_lower for token in ["set of 2", "couple", "couples", "wedding ring set", "matching ring"]):
        return True
    if pick_prop(
        props,
        [
            "Size for Your Partner",
            "Partner Size",
            "His Size",
            "Hers Size",
            "Her Size",
            "Second Ring Size",
            "Ring Size 2",
            "2nd Ring Size",
        ],
    ):
        return True
    text = personalization.lower()
    return bool(re.search(r"\b(his|hers|partner|second|2nd)\b", text))


def _pair_sizes(props: dict, personalization: str) -> tuple[str, str]:
    size1 = pick_prop(
        props,
        [
            "Size for You",
            "Your Size",
            "Her Size",
            "Hers Size",
            "Woman Size",
            "Women Size",
            "First Ring Size",
            "Ring Size 1",
            "1st Ring Size",
            "Ring size",
        ],
    )
    size2 = pick_prop(
        props,
        [
            "Size for Your Partner",
            "Partner Size",
            "His Size",
            "Man Size",
            "Men Size",
            "Second Ring Size",
            "Ring Size 2",
            "2nd Ring Size",
        ],
    )

    text = personalization
    if not size1:
        match = re.search(r"(hers|her|woman|women|your|first|1st)[^0-9]{0,20}(\d+(?:\s+\d+/\d+|/\d+)?(?:\.\d+)?)", text, re.I)
        if match:
            size1 = match.group(2).strip()
    if not size2:
        match = re.search(r"(his|him|man|men|partner|second|2nd)[^0-9]{0,20}(\d+(?:\s+\d+/\d+|/\d+)?(?:\.\d+)?)", text, re.I)
        if match:
            size2 = match.group(2).strip()
    return clean_text(size1), clean_text(size2)


def _pair_widths(props: dict, personalization: str, product: str) -> tuple[str, str]:
    width1 = normalize_width(
        pick_prop(
            props,
            [
                "Width for You",
                "Your Width",
                "Her Width",
                "Hers Width",
                "Woman Width",
                "First Ring Width",
                "Ring Width 1",
                "1st Ring Width",
            ],
        )
    )
    width2 = normalize_width(
        pick_prop(
            props,
            [
                "Width for Your Partner",
                "Partner Width",
                "His Width",
                "Man Width",
                "Second Ring Width",
                "Ring Width 2",
                "2nd Ring Width",
            ],
        )
    )

    text = personalization.lower()
    hers = re.search(r"(hers|her|woman|women)[^:]*:\s*(\d+)\s*mm", text)
    his = re.search(r"(his|him|man|men)[^:]*:\s*(\d+)\s*mm", text)
    if hers:
        width1 = f"{hers.group(2)}MM"
    if his:
        width2 = f"{his.group(2)}MM"
    default_width = normalize_width(pick_prop(props, WIDTH_KEYS) or _width_from_product(product))
    if not width1:
        width1 = default_width or "2MM"
    if not width2:
        width2 = default_width or "4MM"
    return width1, width2


def clean_crss_product(product: str) -> str:
    remove = [
        "14k solid gold",
        "14k gold",
        "solid gold",
        "14k white gold",
        "14k yellow gold",
        "14k rose gold",
        "sterling silver",
        "gold vermeil",
        "white gold vermeil",
        "yellow gold vermeil",
        "rose gold vermeil",
        "14k",
        "solid",
        "dainty",
        "minimalist",
        "personalized",
        "real gold",
        "genuine",
        "handmade",
        "custom",
    ]
    result = product.lower()
    for item in remove:
        result = result.replace(item, " ")
    result = re.sub(r"\s+", " ", result).strip().title()
    return result[:22] + "..." if len(result) > 25 else result


def _props_to_string(props: dict) -> str:
    return ",".join(f"Ad:{k},Değer:{v}" for k, v in props.items())


def _merge_props(groups: list[dict]) -> dict:
    props = {}
    for group in groups:
        for key, value in group.items():
            props.setdefault(key, value)
    return props


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _is_fee_line(product_lower: str) -> bool:
    return any(
        keyword in product_lower
        for keyword in ["price adjustment", "shipping fee", "shipping cost", "additional fee", "extra charge"]
    )
