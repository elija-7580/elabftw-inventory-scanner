"""In-memory label rendering (PDF/PNG). Never writes label files to disk.

Pillow is used only to:
- assemble the PNG label canvas (paste symbol + draw text), and
- wrap pylibdmtx/segno pixel buffers via Image.frombytes / Image.open.

Symbol modules are never resampled (no Image.resize / thumbnail).
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import segno
import yaml
from PIL import Image, ImageDraw, ImageFont
from pylibdmtx.pylibdmtx import encode as dmtx_encode
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .branding import Branding, load_branding

_QR_VERSION = 1
_QR_MODULES = 21  # version 1
_MIN_QUIET = 4


@dataclass(frozen=True)
class LabelContainer:
    """Plain data for label rendering — not an ORM object."""

    scanner_id: str
    chemical_name: str = ""
    storage_location: str = ""
    lot: str = ""
    expiry_date: str = ""


@dataclass(frozen=True)
class LabelFormat:
    key: str
    width_mm: float
    height_mm: float
    qr_mm: float
    text: str  # bottom | right
    rotate: int
    symbol: str  # qr | datamatrix


def _formats_path() -> Path:
    override = os.environ.get("LABEL_FORMATS_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "config" / "label_formats.yaml"


@lru_cache(maxsize=4)
def load_formats(path: str | None = None) -> dict[str, LabelFormat]:
    p = Path(path) if path else _formats_path()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    formats: dict[str, LabelFormat] = {}
    for key, raw in (data or {}).items():
        formats[key] = LabelFormat(
            key=key,
            width_mm=float(raw["w"]),
            height_mm=float(raw["h"]),
            qr_mm=float(raw["qr"]),
            text=str(raw["text"]),
            rotate=int(raw.get("rotate", 0)),
            symbol=str(raw.get("symbol", "qr")),
        )
    return formats


def clear_format_cache() -> None:
    load_formats.cache_clear()
    load_format_defaults.cache_clear()


def get_format(key: str) -> LabelFormat:
    formats = load_formats()
    if key not in formats:
        raise ValueError(f"unknown label format: {key}")
    return formats[key]


def list_format_keys() -> list[str]:
    """Stable ordered list of registered format keys."""
    return list(load_formats().keys())


def _defaults_path() -> Path:
    override = os.environ.get("LABEL_FORMAT_DEFAULTS_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "config" / "label_format_defaults.yaml"


@lru_cache(maxsize=4)
def load_format_defaults(path: str | None = None) -> dict[int, str]:
    """category_id → format key. Unknown / missing keys are ignored."""
    p = Path(path) if path else _defaults_path()
    if not p.is_file():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    known = load_formats()
    out: dict[int, str] = {}
    for key, value in raw.items():
        try:
            cid = int(key)
        except (TypeError, ValueError):
            continue
        fmt = str(value).strip()
        if fmt in known:
            out[cid] = fmt
    return out


def clear_format_defaults_cache() -> None:
    load_format_defaults.cache_clear()


def default_format_for_category(category_id: int | None) -> str | None:
    """Return mapped format key, or None when the operator must pick."""
    if category_id is None:
        return None
    return load_format_defaults().get(int(category_id))


def resolve_label_format(category_id: int | None, requested: str | None = None) -> str:
    """Prefer explicit request, then category default, else first registry key."""
    keys = list_format_keys()
    if not keys:
        raise ValueError("no label formats configured")
    if requested:
        get_format(requested)
        return requested
    mapped = default_format_for_category(category_id)
    if mapped:
        return mapped
    return keys[0]


def label_payload(scanner_id: str) -> str:
    mode = os.environ.get("LABEL_PAYLOAD_MODE", "id").strip().lower()
    if mode == "url":
        base = os.environ.get("LABEL_URL_BASE", "").rstrip("/")
        if not base:
            raise ValueError("LABEL_URL_BASE required when LABEL_PAYLOAD_MODE=url")
        return f"{base}/{scanner_id}"
    return scanner_id


def _truncate(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "…"


def _assert_qr_version_1(payload: str) -> None:
    """Refuse payloads that would force a denser QR version than 1."""
    if len(payload) > 20:
        raise ValueError("payload too large for QR version 1 (ECC M)")
    qr = segno.make(payload, error="M", boost_error=False, micro=False)
    if qr.version != _QR_VERSION:
        raise ValueError(
            f"payload requires QR version {qr.version}, only version {_QR_VERSION} allowed"
        )


def _use_datamatrix(fmt: LabelFormat) -> bool:
    return fmt.symbol == "datamatrix" or fmt.qr_mm < 20


def _qr_drawing(payload: str, size: float) -> Drawing:
    _assert_qr_version_1(payload)
    modules = _QR_MODULES + 2 * _MIN_QUIET
    module = size / modules
    widget = QrCodeWidget(payload)
    widget.barLevel = "M"
    widget.barBorder = _MIN_QUIET
    widget.barWidth = module * modules
    widget.barHeight = module * modules
    d = Drawing(size, size)
    d.add(widget)
    return d


def _datamatrix_image(payload: str, module_px: int = 1) -> Image.Image:
    """Encode ECC200 DataMatrix via libdmtx.

    `module_px` is retained for API compatibility but libdmtx controls module
    geometry; we never resample the returned bitmap (nearest-neighbour or
    otherwise). Quiet zone is ensured by white padding only.
    """
    del module_px  # libdmtx encode() has no module_width in this binding
    encoded = dmtx_encode(payload.encode("utf-8"))
    img = Image.frombytes("RGB", (encoded.width, encoded.height), encoded.pixels)
    # Ensure quiet zone >= 4 modules by padding if corners are not white.
    # Estimate module size from first dark run; fall back to 1 px.
    module_est = 1
    need_pad = False
    for x, y in ((0, 0), (img.width - 1, 0), (0, img.height - 1), (img.width - 1, img.height - 1)):
        px = img.getpixel((x, y))
        if px[0] < 250 or px[1] < 250 or px[2] < 250:
            need_pad = True
            break
    quiet_px = _MIN_QUIET * module_est
    if need_pad:
        canvas_img = Image.new(
            "RGB",
            (img.width + 2 * quiet_px, img.height + 2 * quiet_px),
            "white",
        )
        canvas_img.paste(img, (quiet_px, quiet_px))
        return canvas_img
    return img


def _qr_png(payload: str, target_px: int) -> Image.Image:
    _assert_qr_version_1(payload)
    total_modules = _QR_MODULES + 2 * _MIN_QUIET
    module_px = max(1, target_px // total_modules)
    qr = segno.make(payload, error="M", boost_error=False, micro=False)
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=module_px, border=_MIN_QUIET)
    # Image.open only wraps already-rasterised integer-module PNG — no resize.
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _symbol_image(payload: str, fmt: LabelFormat, size_px: int) -> Image.Image:
    if _use_datamatrix(fmt):
        # Native libdmtx pixels only — never scale down/up after encode.
        return _datamatrix_image(payload)
    return _qr_png(payload, size_px)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _draw_brand_face_png(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    brand: Branding,
    fmt: LabelFormat,
) -> None:
    """Human-readable brand mark only — never part of the QR/DataMatrix payload."""
    accent = _hex_to_rgb(brand.accent_hex)
    bar_h = 2 if fmt.height_mm < 15 else 3
    # Bottom accent strip — keeps QR/DM (usually top/left) clear.
    draw.rectangle((0, img.height - bar_h, img.width, img.height), fill=accent)
    font = ImageFont.load_default()
    brand_text = _truncate(brand.product_name, 18 if fmt.width_mm < 30 else 28)
    if brand_text:
        tw = (
            draw.textlength(brand_text, font=font)
            if hasattr(draw, "textlength")
            else len(brand_text) * 6
        )
        x = max(2, img.width - int(tw) - 3)
        y = max(0, img.height - bar_h - 10)
        draw.text((x, y), brand_text, fill=accent, font=font)
    if brand.logo_path and fmt.height_mm >= 20 and fmt.width_mm >= 30:
        try:
            logo = Image.open(brand.logo_path).convert("RGBA")
            max_h = min(18, max(1, img.height // 5))
            max_w = min(36, max(1, img.width // 4))
            # Paste only when native pixels fit — never resample logo (or code modules).
            if logo.width <= max_w and logo.height <= max_h:
                img.paste(logo, (2, 2), logo)
        except OSError:
            pass


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    container: LabelContainer,
    fmt: LabelFormat,
) -> None:
    font = ImageFont.load_default()
    x, y = xy
    name = _truncate(container.chemical_name, 24)
    if name:
        draw.text((x, y), name, fill="black", font=font)
        y += 11
    draw.text((x, y), container.scanner_id, fill="black", font=font)
    y += 11
    loc = _truncate(container.storage_location, 24)
    if loc:
        draw.text((x, y), loc, fill="black", font=font)
        y += 11
    if fmt.height_mm >= 20 or (fmt.width_mm >= 30 and fmt.height_mm >= 30):
        extra = " ".join(
            part
            for part in (
                f"Lot {container.lot}" if container.lot else "",
                f"Exp {container.expiry_date}" if container.expiry_date else "",
            )
            if part
        )
        if extra:
            draw.text((x, y), _truncate(extra, 28), fill="black", font=font)


def _draw_brand_face_pdf(
    c: canvas.Canvas,
    brand: Branding,
    fmt: LabelFormat,
    width: float,
    height: float,
) -> None:
    """Human-readable brand mark only — never part of the QR/DataMatrix payload."""
    accent = HexColor(brand.accent_hex)
    bar_h = 0.6 * mm if fmt.height_mm < 15 else 1.0 * mm
    # Bottom accent strip — keeps QR/DM (usually top/left) clear.
    c.setFillColor(accent)
    c.rect(0, 0, width, bar_h, fill=1, stroke=0)
    brand_text = _truncate(brand.product_name, 18 if fmt.width_mm < 30 else 28)
    if brand_text:
        c.setFillColor(accent)
        c.setFont("Helvetica", 5)
        c.drawRightString(width - 1 * mm, bar_h + 0.8 * mm, brand_text)
    if brand.logo_path and fmt.height_mm >= 20 and fmt.width_mm >= 30:
        try:
            reader = ImageReader(brand.logo_path)
            logo_h = 4 * mm
            logo_w = 4 * mm
            c.drawImage(
                reader,
                1 * mm,
                height - logo_h - 0.5 * mm,
                width=logo_w,
                height=logo_h,
                mask="auto",
                preserveAspectRatio=True,
            )
        except OSError:
            pass
    c.setFillColor(HexColor("#000000"))


def _pdf_label(container: LabelContainer, fmt: LabelFormat) -> bytes:
    payload = label_payload(container.scanner_id)
    brand = load_branding()
    width = fmt.width_mm * mm
    height = fmt.height_mm * mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    symbol_size = fmt.qr_mm * mm
    if _use_datamatrix(fmt):
        # Embed integer-module PNG; reportlab places it at target size in points
        # without resampling the source (ImageReader streams original pixels).
        dm = _datamatrix_image(payload)
        dm_buf = io.BytesIO()
        dm.save(dm_buf, format="PNG")
        dm_buf.seek(0)
        reader = ImageReader(dm_buf)
        if fmt.text == "bottom":
            sx = (width - symbol_size) / 2
            sy = height - symbol_size - 1 * mm
            text_x, text_y = 1 * mm, 4 * mm
        else:
            sx = 1 * mm
            sy = (height - symbol_size) / 2
            text_x = sx + symbol_size + 1 * mm
            text_y = height - 3 * mm
        c.drawImage(reader, sx, sy, width=symbol_size, height=symbol_size, mask="auto")
    else:
        drawing = _qr_drawing(payload, symbol_size)
        if fmt.text == "bottom":
            sx = (width - symbol_size) / 2
            sy = height - symbol_size - 1 * mm
            text_x, text_y = 1 * mm, 4 * mm
        else:
            sx = 1 * mm
            sy = (height - symbol_size) / 2
            text_x = sx + symbol_size + 1 * mm
            text_y = height - 3 * mm
        renderPDF.draw(drawing, c, sx, sy)

    c.setFont("Helvetica", 6)
    name = _truncate(container.chemical_name, 28)
    if name:
        c.drawString(text_x, text_y, name)
    c.setFont("Courier", 6)
    c.drawString(text_x, text_y - 8, container.scanner_id)
    c.setFont("Helvetica", 5)
    loc = _truncate(container.storage_location, 24)
    if loc:
        c.drawString(text_x, text_y - 15, loc)
    if fmt.height_mm >= 20 or (fmt.width_mm >= 30 and fmt.height_mm >= 30):
        extra = " ".join(
            part
            for part in (
                f"Lot {container.lot}" if container.lot else "",
                f"Exp {container.expiry_date}" if container.expiry_date else "",
            )
            if part
        )
        if extra:
            c.drawString(text_x, text_y - 22, _truncate(extra, 32))

    _draw_brand_face_pdf(c, brand, fmt, width, height)

    c.showPage()
    c.save()
    return buf.getvalue()


def _png_label(container: LabelContainer, fmt: LabelFormat, dpi: int) -> bytes:
    payload = label_payload(container.scanner_id)
    brand = load_branding()
    w_px = max(1, int(round(fmt.width_mm / 25.4 * dpi)))
    h_px = max(1, int(round(fmt.height_mm / 25.4 * dpi)))
    symbol_px = max(1, int(round(fmt.qr_mm / 25.4 * dpi)))

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)
    symbol = _symbol_image(payload, fmt, symbol_px)

    # Layout in final page coordinates — never rotate/resample the symbol bitmap.
    # fmt.rotate describes physical label orientation; page size already matches w×h.
    if fmt.text == "bottom":
        sx = max(0, (w_px - symbol.width) // 2)
        sy = 2
        text_xy = (4, min(h_px - 12, symbol.height + 4))
    else:
        sx = 2
        sy = max(0, (h_px - symbol.height) // 2)
        text_xy = (min(w_px - 4, symbol.width + 6), 4)

    # Clip-paste if symbol exceeds canvas (integer crop, no resample)
    if symbol.width > w_px or symbol.height > h_px:
        symbol = symbol.crop((0, 0, min(symbol.width, w_px), min(symbol.height, h_px)))
    img.paste(symbol, (sx, sy))
    _draw_text_block(draw, text_xy, container, fmt)
    _draw_brand_face_png(draw, img, brand, fmt)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_label(
    container: LabelContainer, fmt: str, output: str, *, dpi: int = 300
) -> bytes:
    """Pure function: render_label(container, fmt, output) -> bytes."""
    if output not in ("pdf", "png"):
        raise ValueError(f"unsupported output: {output}")
    label_fmt = get_format(fmt)
    if output == "pdf":
        return _pdf_label(container, label_fmt)
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    return _png_label(container, label_fmt, dpi)


def pdf_page_size_mm(pdf_bytes: bytes) -> tuple[float, float]:
    """Return (width_mm, height_mm) of the first PDF page from MediaBox."""
    m = re.search(
        rb"/MediaBox\s*\[\s*([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*\]",
        pdf_bytes,
    )
    if not m:
        raise ValueError("MediaBox not found")
    x0, y0, x1, y1 = map(float, m.groups())
    return (x1 - x0) / mm, (y1 - y0) / mm


def qr_module_count(payload: str) -> int:
    qr = segno.make(payload, error="M", boost_error=False, micro=False)
    return int(qr.symbol_size(border=0)[0])


def qr_has_quiet_zone(payload: str, module_px: int = 4) -> bool:
    """True when rendered PNG has white quiet zone >= 4 modules."""
    img = _qr_png(payload, (_QR_MODULES + 2 * _MIN_QUIET) * module_px)
    px = img.getpixel((0, 0))
    return px[0] >= 250 and px[1] >= 250 and px[2] >= 250 and img.width >= (
        _QR_MODULES + 2 * _MIN_QUIET
    ) * module_px
