from __future__ import annotations

import io
import zipfile

import pandas as pd
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from utils import (
    clean_text,
    convert_size_to_decimal,
    model_priority,
    now_tr,
    turkce_to_ascii,
    width_numeric,
)


def create_pdf_labels(orders_df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    label_width, label_height = 5 * cm, 3 * cm
    margin_x, margin_y = 0.2 * cm, 0.2 * cm
    gap_x, gap_y = 0.15 * cm, 0.15 * cm
    labels_per_row, labels_per_column = 4, 9
    labels_per_page = labels_per_row * labels_per_column

    for label_count, (_, row) in enumerate(orders_df.iterrows()):
        if label_count > 0 and label_count % labels_per_page == 0:
            c.showPage()
        col = label_count % labels_per_row
        row_num = (label_count // labels_per_row) % labels_per_column
        x = margin_x + col * (label_width + gap_x)
        y = page_height - margin_y - ((row_num + 1) * (label_height + gap_y))
        draw_label(c, x, y, label_width, label_height, row)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def draw_label(c, x, y, width, height, data):
    urgent = is_urgent_order(data)
    emphasis = has_label_emphasis(data)
    border_color = HexColor("#d00000") if urgent else black
    c.setStrokeColor(border_color)
    c.setLineWidth(2 if urgent else 1)
    c.rect(x, y, width, height)
    if urgent:
        band_h = 0.32 * cm
        c.setFillColor(HexColor("#d00000"))
        c.rect(x, y + height - band_h, width, band_h, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(x + width / 2, y + height - 0.23 * cm, "ACIL / ONCELIKLI")
        c.setFillColor(black)
    text_x = x + 0.1 * cm
    value_x = x + 1.7 * cm
    font_size = 7
    store = clean_text(data.get("Mağaza")).lower()
    coklu = str(data.get("Çoklu", "")).upper() in {"TRUE", "1", "DOĞRU"}

    if store == "crss" or "cerasus" in store:
        store_line = label_store_line("CRSS", coklu, data)
        rows = [
            ("Magaza", store_line),
            ("Siparis No", data.get("Sipariş No", "")),
            ("Musteri", turkce_to_ascii(clean_text(data.get("Müşteri"))[:20])),
            ("Urun", turkce_to_ascii(clean_text(data.get("Ürün") or data.get("Model"))[:25])),
            ("Olcu/Zincir", data.get("Ölçü", "")),
            ("Renk", turkce_to_ascii(clean_text(data.get("Renk"))[:18])),
            ("Not", turkce_to_ascii(clean_text(data.get("Kişiselleştirme"))[:30])),
        ]
        min_rows = 7
    else:
        pers = clean_text(data.get("Kişiselleştirme"))
        line1, line2 = split_text(pers, 30)
        store_line = label_store_line(clean_text(data.get("Mağaza")), coklu, data)
        rows = [
            ("Magaza", store_line),
            ("Siparis No", data.get("Sipariş No", "")),
            ("Musteri Adi", turkce_to_ascii(clean_text(data.get("Müşteri"))[:25])),
            ("Genislik", data.get("Genişlik", "")),
            ("Renk", turkce_to_ascii(clean_text(data.get("Renk"))[:18])),
            ("Model", turkce_to_ascii(clean_text(data.get("Model")))),
            ("Olcu", data.get("Ölçü", "")),
            ("Lazer", line1),
        ]
        if line2:
            rows.append(("", line2))
        note = clean_text(data.get("Özel Not"))
        if note:
            rows.append(("Not", turkce_to_ascii(note[:30])))
        min_rows = 8

    content_top_offset = 0.32 * cm if urgent else 0
    usable_height = height - content_top_offset
    row_count = max(min_rows, len(rows))
    line_height = usable_height / row_count
    font_size = 7 if row_count <= 8 else 6
    for i in range(1, row_count):
        c.setLineWidth(0.3)
        c.line(x, y + i * line_height, x + width, y + i * line_height)
    max_value_w = width - 1.8 * cm
    for i, (label, value) in enumerate(rows):
        row_y = y + usable_height - ((i + 0.65) * line_height)
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(text_x, row_y, clean_text(label))
        val = clean_text(value)
        value_font = "Helvetica-Bold" if emphasis else "Helvetica"
        base_value_size = font_size if emphasis else font_size - 1
        val_font, val = fit_text(c, turkce_to_ascii(val), value_font, base_value_size, max_value_w, min_size=4)
        c.setFont(value_font, val_font)
        c.drawString(value_x, row_y, val)


def create_lazer_labels(orders_df: pd.DataFrame) -> bytes | None:
    personalized = orders_df[
        orders_df["Kişiselleştirme"].fillna("").astype(str).str.strip().replace("nan", "") != ""
    ].copy()
    if personalized.empty:
        return None

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    label_width, label_height = 9.5 * cm, 5.0 * cm
    margin_x, margin_y = 0.5 * cm, 0.5 * cm
    gap_x, gap_y = 0.3 * cm, 0.3 * cm
    labels_per_row, labels_per_column = 2, 5
    labels_per_page = labels_per_row * labels_per_column

    for label_count, (_, row) in enumerate(personalized.iterrows()):
        if label_count > 0 and label_count % labels_per_page == 0:
            c.showPage()
        col = label_count % labels_per_row
        row_num = (label_count // labels_per_row) % labels_per_column
        x = margin_x + col * (label_width + gap_x)
        y = page_height - margin_y - ((row_num + 1) * (label_height + gap_y))
        draw_lazer_label(c, x, y, label_width, label_height, row)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def draw_lazer_label(c, x, y, width, height, data):
    c.setStrokeColor(HexColor("#ff8c00"))
    c.setLineWidth(1.5)
    c.rect(x, y, width, height)
    text_x = x + 0.2 * cm
    label_col_w = 2.0 * cm
    font_size = 8

    c.setFillColor(HexColor("#cc6600"))
    c.setFont("Helvetica-Bold", font_size + 1)
    c.drawString(text_x, y + height - 0.5 * cm, "LAZER ETIKETI")
    c.setFillColor(black)
    c.setStrokeColor(HexColor("#ff8c00"))
    c.line(x, y + height - 0.7 * cm, x + width, y + height - 0.7 * cm)

    rows = [
        ("Musteri:", turkce_to_ascii(clean_text(data.get("Müşteri"))[:35])),
        ("Genislik:", data.get("Genişlik", "")),
        ("Renk:", turkce_to_ascii(clean_text(data.get("Renk"))[:18])),
        ("Olcu:", data.get("Ölçü", "")),
    ]
    row_y = y + height - 1.1 * cm
    for label, value in rows:
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(text_x, row_y, label)
        max_w = width - label_col_w - 0.4 * cm
        val_font, val = fit_text(c, turkce_to_ascii(clean_text(value)), "Helvetica", font_size, max_w, min_size=5)
        c.setFont("Helvetica", val_font)
        c.drawString(text_x + label_col_w, row_y, val)
        row_y -= 0.55 * cm

    c.setFont("Helvetica-Bold", font_size)
    c.drawString(text_x, row_y, "Lazer:")
    c.setFont("Helvetica", font_size)
    pers = turkce_to_ascii(clean_text(data.get("Kişiselleştirme")))
    chars_per_line = max(20, int((width - label_col_w - 0.4 * cm) / (font_size * 0.52)))
    for i in range(4):
        chunk = pers[i * chars_per_line : (i + 1) * chars_per_line]
        if not chunk:
            break
        lx = text_x + label_col_w if i == 0 else text_x + 0.3 * cm
        max_w = width - (lx - x) - 0.3 * cm
        val_font, val = fit_text(c, chunk, "Helvetica", font_size, max_w, min_size=5)
        c.setFont("Helvetica", val_font)
        c.drawString(lx, row_y - i * 0.52 * cm, val)


def create_uretim_listesi(orders_df: pd.DataFrame) -> str:
    production = orders_df[orders_df["Model"].astype(str) != "YENİLEME"].copy()
    if production.empty:
        return "Üretim gerektiren sipariş yok."

    production["Ölçü_Ondalık"] = production["Ölçü"].apply(convert_size_to_decimal)
    production["Ölçü_Sayısal"] = production["Ölçü_Ondalık"].astype(float)
    production["Model_Öncelik"] = production["Model"].apply(model_priority)
    production["Genişlik_Sayısal"] = production["Genişlik"].apply(width_numeric)
    production = production.sort_values(["Model_Öncelik", "Genişlik_Sayısal", "Ölçü_Sayısal"])

    output = "Üretim Listesi\n==============\n\n"
    output += f"{'Genişlik':<10}{'Model':<15}{'Ölçü (Ondalık)':<20}Müşteri\n"
    output += f"{'-'*9} {'-'*14} {'-'*19} {'-'*24}\n"
    for _, row in production.iterrows():
        output += f"{clean_text(row['Genişlik']):<10}{clean_text(row['Model']):<15}{clean_text(row['Ölçü_Ondalık']):<20}{clean_text(row['Müşteri'])}\n"

    yenileme = orders_df[orders_df["Model"].astype(str) == "YENİLEME"]
    for _, row in yenileme.iterrows():
        output += f"{'':<10}{'':<15}{clean_text(row.get('Ölçü')):<20}{clean_text(row.get('Müşteri'))} YENİLEME\n"

    output += "\n\nÜretim Listesi (Kopyalama için - İsimsiz)\n"
    output += "==========================================\n\n"
    output += f"{'Genişlik':<10}{'Model':<15}{'Ölçü (Ondalık)':<20}\n"
    output += f"{'-'*9} {'-'*14} {'-'*19}\n"
    for _, row in production.iterrows():
        output += f"{clean_text(row['Genişlik']):<10}{clean_text(row['Model']):<15}{clean_text(row['Ölçü_Ondalık']):<20}\n"
    return output


def create_kisisellestirme_listesi(orders_df: pd.DataFrame) -> str:
    personalized = orders_df[
        orders_df["Kişiselleştirme"].fillna("").astype(str).str.strip().replace("nan", "") != ""
    ].copy()
    if personalized.empty:
        return "Kişiselleştirme gerektiren sipariş yok."
    output = "Kişiselleştirme Listesi\n=======================\n\n"
    for _, row in personalized.iterrows():
        output += (
            f"Müşteri: {clean_text(row.get('Müşteri'))}\n"
            f"Genişlik: {clean_text(row.get('Genişlik'))}\n"
            f"Ölçü: {clean_text(row.get('Ölçü'))}\n"
            f"Kişiselleştirme:\n   {clean_text(row.get('Kişiselleştirme')).replace(chr(10), chr(10) + '   ')}\n"
            + "-" * 80
            + "\n\n"
        )
    return output


def create_kontrol_listesi(orders_df: pd.DataFrame, store_name: str = "") -> bytes:
    buffer = io.BytesIO()
    page_w, page_h = A4
    margin = 1 * cm
    usable_w = page_w - 2 * margin
    col_ratios = [0.16, 0.18, 0.08, 0.09, 0.10, 0.10, 0.23, 0.06]
    labels = ["Siparis No", "Musteri Adi", "Genislik", "Renk", "Model", "Olcu", "Kisisellestirme", "CHECK"]
    widths = [usable_w * r for r in col_ratios]
    n = len(orders_df)
    font_size, row_h = (8, 1.0 * cm) if n <= 15 else ((7, 0.85 * cm) if n <= 25 else (6, 0.72 * cm))
    header_h = row_h * 1.3
    c = canvas.Canvas(buffer, pagesize=A4)

    def header(y_start):
        c.setFont("Helvetica-Bold", font_size + 1)
        c.drawString(margin, y_start + 0.3 * cm, turkce_to_ascii(f"Magaza: {store_name} | Kontrol Listesi | {now_tr()}"))
        y = y_start - 0.1 * cm
        c.setFillColor(HexColor("#444444"))
        c.rect(margin, y - header_h, usable_w, header_h, fill=1, stroke=0)
        c.setFillColor(HexColor("#ffffff"))
        c.setFont("Helvetica-Bold", font_size)
        x = margin
        for label, w in zip(labels, widths):
            c.drawString(x + 3, y - header_h + 4, label)
            x += w
        c.setFillColor(black)
        return y - header_h

    y = header(page_h - margin - 0.6 * cm)
    for i, (_, row) in enumerate(orders_df.iterrows()):
        if y - row_h < margin:
            c.showPage()
            y = header(page_h - margin - 0.6 * cm)
        if i % 2 == 0:
            c.setFillColor(HexColor("#f5f5f5"))
            c.rect(margin, y - row_h, usable_w, row_h, fill=1, stroke=0)
            c.setFillColor(black)
        vals = [
            row.get("Sipariş No", ""),
            turkce_to_ascii(row.get("Müşteri", "")),
            row.get("Genişlik", ""),
            turkce_to_ascii(row.get("Renk", "")),
            turkce_to_ascii(row.get("Model", "")),
            row.get("Ölçü", ""),
            turkce_to_ascii(clean_text(row.get("Kişiselleştirme")).replace("\n", " ")),
            "[ ]",
        ]
        missing = any(not clean_text(row.get(col)) for col in ["Genişlik", "Renk", "Model"] if row.get("Mağaza") != "CRSS")
        urgent = is_urgent_order(row)
        emphasis = has_label_emphasis(row)
        c.setFillColor(HexColor("#d00000") if urgent else black)
        c.setFont("Helvetica-Bold" if missing or emphasis else "Helvetica", font_size)
        x = margin
        for val, w in zip(vals, widths):
            max_chars = max(4, int(w / (font_size * 0.58)))
            c.drawString(x + 3, y - row_h + 4, clean_text(val)[:max_chars])
            x += w
        c.setStrokeColor(HexColor("#cccccc"))
        c.line(margin, y - row_h, margin + usable_w, y - row_h)
        c.setStrokeColor(black)
        c.setFillColor(black)
        y -= row_h

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def build_files(orders_df: pd.DataFrame) -> dict:
    store_names = sorted({clean_text(v) for v in orders_df.get("Mağaza", pd.Series(dtype=str)).dropna() if clean_text(v)})
    store_name = "-".join(store_names) if store_names else "siparis"
    ts = now_tr("%Y%m%d_%H%M%S")
    prefix = f"{now_tr('%d-%m')}-{store_name}"
    files = {
        "prefix": prefix,
        "kargo_pdf": create_pdf_labels(orders_df),
        "lazer_pdf": create_lazer_labels(orders_df),
        "uretim_txt": create_uretim_listesi(orders_df).encode("utf-8"),
        "kisisel_txt": create_kisisellestirme_listesi(orders_df).encode("utf-8"),
        "kontrol_pdf": create_kontrol_listesi(orders_df, store_name),
    }
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"kargo_etiketleri_{ts}.pdf", files["kargo_pdf"])
        if files["lazer_pdf"]:
            zf.writestr(f"lazer_etiketleri_{ts}.pdf", files["lazer_pdf"])
        zf.writestr(f"fsm_uretim_{ts}.txt", files["uretim_txt"])
        zf.writestr(f"kisisellestirme_{ts}.txt", files["kisisel_txt"])
        zf.writestr(f"kontrol_{ts}.pdf", files["kontrol_pdf"])
    files["zip"] = zip_buffer.getvalue()
    return files


def split_text(text: str, limit: int) -> tuple[str, str]:
    text = clean_text(text)
    if len(text) <= limit:
        return text, ""
    cut = text[:limit].rfind(" ")
    if cut <= 0:
        cut = limit
    return text[:cut], text[cut: limit * 2].strip()


def fit_text(c, text: str, font_name: str, font_size: float, max_width: float, min_size: float = 4) -> tuple[float, str]:
    text = clean_text(text)
    size = font_size
    while size > min_size and c.stringWidth(text, font_name, size) > max_width:
        size -= 0.5
    if c.stringWidth(text, font_name, size) <= max_width:
        return size, text

    ellipsis = "..."
    available = max_width - c.stringWidth(ellipsis, font_name, size)
    if available <= 0:
        return size, ""
    clipped = text
    while clipped and c.stringWidth(clipped, font_name, size) > available:
        clipped = clipped[:-1]
    return size, clipped.rstrip() + ellipsis


def is_urgent_order(data) -> bool:
    fields = [
        clean_text(data.get("Durum")),
        clean_text(data.get("Özel Not")),
        clean_text(data.get("Kişiselleştirme")),
        clean_text(data.get("Ürün")),
    ]
    text = " ".join(fields).upper()
    return any(token in text for token in ["ACİL", "ACIL", "URGENT", "PRIORITY", "ÖNCELİK", "ONCELIK"])


def has_label_emphasis(data) -> bool:
    durum = clean_text(data.get("Durum")).upper()
    return durum in {"ACİL", "ACIL", "10K GOLD", "14K GOLD", "18K GOLD", "DİKKAT", "DIKKAT"}


def label_store_line(store: str, coklu: bool, data) -> str:
    parts = [clean_text(store)]
    if coklu:
        parts.append("COKLU")
    durum = turkce_to_ascii(clean_text(data.get("Durum"))).upper()
    if durum:
        parts.append(durum)
    return " ".join(part for part in parts if part)
