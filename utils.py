from __future__ import annotations

import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


ISTANBUL = ZoneInfo("Europe/Istanbul")


def now_tr(fmt: str = "%d.%m.%Y %H:%M") -> str:
    return datetime.now(ISTANBUL).strftime(fmt)


def turkce_to_ascii(text) -> str:
    if text is None:
        return ""
    if isinstance(text, float) and math.isnan(text):
        return ""
    text = str(text)
    mapping = {
        "ı": "i",
        "İ": "I",
        "ş": "s",
        "Ş": "S",
        "ğ": "g",
        "Ğ": "G",
        "ü": "u",
        "Ü": "U",
        "ö": "o",
        "Ö": "O",
        "ç": "c",
        "Ç": "C",
    }
    for src, dst in mapping.items():
        text = text.replace(src, dst)
    return text


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value)
    return (
        text.replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
        .replace("\\n", "\n")
        .strip()
    )


def norm_key(value) -> str:
    text = turkce_to_ascii(clean_text(value)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def pick_prop(props: dict, names: list[str], default: str = "") -> str:
    normalized = {norm_key(k): clean_text(v) for k, v in props.items()}
    for name in names:
        value = normalized.get(norm_key(name), "")
        if value and value.lower() not in {"nan", "none", "null"}:
            return value
    return default


def normalize_width(width: str) -> str:
    width = clean_text(width).upper()
    if not width:
        return ""
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*MM", width, re.I) or re.search(r"(\d+(?:[.,]\d+)?)", width)
    if not match:
        return width
    number = match.group(1).replace(",", ".")
    if number.endswith(".0"):
        number = number[:-2]
    return f"{number}MM"


def normalize_color(color: str, product: str = "") -> str:
    source = f"{color} {product}".lower()
    if "mat" in source and ("white" in source or "beyaz" in source):
        return "MAT BEYAZ"
    if "mat" in source and ("yellow" in source or "sari" in turkce_to_ascii(source).lower()):
        return "MAT SARI"
    if "mat" in source and "rose" in source:
        return "MAT ROSE"
    if "white" in source or "beyaz" in source or "silver" in source:
        if "sterling" in source:
            return "Sterling Silver"
        return "BEYAZ"
    if "yellow" in source or "sari" in turkce_to_ascii(source).lower() or "gold filled" in source:
        if "14k" in source:
            return "14K Yellow Gold"
        return "SARI"
    if "rose" in source or "pembe" in source:
        if "14k" in source:
            return "14K Rose Gold"
        return "ROSE"
    return clean_text(color)


def parse_order_date(value):
    text = clean_text(value)
    if not text:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=ISTANBUL) if dt.tzinfo is None else dt
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(ISTANBUL)
    except ValueError:
        return None


def convert_size_to_decimal(size_str) -> str:
    text = clean_text(size_str).replace(" US", "").replace("US", "").strip()
    if not text:
        return "0.00"
    try:
        if "/" in text:
            parts = text.split()
            if len(parts) == 2:
                whole = int(parts[0])
                num, den = parts[1].split("/")
                value = whole + int(num) / int(den)
            else:
                num, den = parts[0].split("/")
                value = int(num) / int(den)
        else:
            value = float(text)
        return f"{value:.2f}"
    except Exception:
        return "0.00"


def model_priority(model) -> int:
    text = norm_key(model)
    if "bombe" in text or "dome" in text:
        return 1
    if "cati" in text or "bevel" in text:
        return 2
    if "duz" in text or "flat" in text:
        return 3
    if "oval" in text or "tektas" in text or "solitaire" in text:
        return 4
    return 5


def width_numeric(width) -> float:
    match = re.search(r"(\d+(?:[.,]\d+)?)", clean_text(width))
    return float(match.group(1).replace(",", ".")) if match else 0.0
