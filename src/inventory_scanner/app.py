"""FastAPI BFF for inventory scanner (server-side eLabFTW access)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from .audit import AuditLedger
from .auth import install_auth_middleware, oidc_enabled, router as auth_router
from .barcode import classify_scan
from .catalog import ProductCatalog, normalize_code
from .catalog_import import commit_import, mapping_from_form, prepare_import, read_upload
from .elab_client import ElabApiClient
from .extra_fields import build_corrected_item_metadata, extract_legacy_poc_fields
from .inventory_options import load_inventory_options
from .inventory_validation import validate_category_id, validate_storage_id
from .matching import assess_candidate_confidence, match_compound_exact, match_item_exact, product_identity_key
from .pack_lines import expand_pack_lines, format_pack_line, validate_pack_lines
from .writes import require_writes, writes_enabled
from .version import git_commit


class StaticCacheMiddleware(BaseHTTPMiddleware):
    """HTML revalidates; content-hashed JS is immutable."""

    async def dispatch(self, request: StarletteRequest, call_next) -> StarletteResponse:
        response = await call_next(request)
        path = request.url.path
        if path.endswith(".html") or path == "/":
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        elif "/js/scanner-app." in path and path.endswith(".js"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


class ScanPayload(BaseModel):
    raw_value: str
    symbology: str = "unknown"


class PackLinePayload(BaseModel):
    amount_per_container: float
    unit: str
    container_count: int | None = None  # ignored; one UI line = one container


class RegisterConfirmPayload(BaseModel):
    manufacturer: str
    catalogue_number: str
    product_name: str
    category_id: int | None = None
    storage_id: int | None = None
    lines: list[PackLinePayload] = Field(default_factory=list)
    original_barcode: str = ""
    lot_batch: str = ""
    expiry_date: str = ""
    cas_number: str = ""
    pubchem_cid: str = ""
    compound_id: int | None = None
    create_compound: bool = False
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ContainerActionPayload(BaseModel):
    operation: str  # consume | restock | set_exact | mark_empty
    qty: float | None = None
    unit: str | None = None
    manufacturer: str | None = None
    catalogue_number: str | None = None
    product_name: str | None = None
    lot_batch: str | None = None
    expiry_date: str | None = None
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))


class CatalogLookupPayload(BaseModel):
    code: str = ""
    manufacturer: str = ""
    catalogue_number: str = ""
    catalog_number: str = ""


class CatalogSavePayload(BaseModel):
    product_name: str = ""
    manufacturer: str = ""
    catalogue_number: str = ""
    catalog_number: str = ""
    cas_number: str = ""
    primary_code: str = ""
    alternate_codes: list[str] = Field(default_factory=list)
    category_id: int | None = None
    confirm: bool = False


def _web_root() -> Path:
    override = os.environ.get("SCANNER_WEB_DIR", "").strip()
    if override:
        return Path(override)
    candidate = Path(__file__).resolve().parents[2] / "web" / "dist"
    if candidate.is_dir():
        return candidate
    return Path("/app/web/dist")


def _client() -> ElabApiClient:
    return ElabApiClient.from_env()


def _session_user(request: Request) -> tuple[str, str]:
    user = request.session.get("user") or {}
    return (
        str(user.get("sub") or user.get("email") or os.environ.get("SCANNER_USER_ID", "bff-service")),
        str(user.get("email") or os.environ.get("SCANNER_USER_EMAIL", "")),
    )


def _item_fields_from_payload(item: dict[str, Any]) -> dict[str, str]:
    meta = item.get("metadata")
    if isinstance(meta, str):
        import json

        meta = json.loads(meta)
    return extract_legacy_poc_fields(meta or {})


def _elab_error(exc: Exception) -> HTTPException:
    return HTTPException(502, f"eLab API error: {exc}")


def create_app() -> FastAPI:
    application = FastAPI(title="Inventory Scanner for eLabFTW", version="0.1.0")

    @application.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if not isinstance(detail, str):
            detail = str(detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    application.add_middleware(StaticCacheMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[os.environ.get("SCANNER_CORS_ORIGIN", "https://elab.example.com")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )
    install_auth_middleware(application)

    db_path = Path(os.environ.get("SCANNER_DB_PATH", "./data/ledger.db"))
    ledger = AuditLedger(db_path)
    catalog = ProductCatalog(db_path)

    def _known_category_ids() -> set[int] | None:
        """Best-effort category id set for import validation; None skips remote check."""
        try:
            team_id = int(os.environ.get("SCANNER_TEAM_ID", "1"))
            options = load_inventory_options(_client(), team_id=team_id)
            cats = options.get("categories") or []
            return {int(c["id"]) for c in cats if c.get("id") is not None}
        except Exception:
            return None

    application.include_router(auth_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "commit": git_commit()}

    @application.get("/api/config/public")
    def public_config() -> dict[str, Any]:
        """Browser-safe config — no secrets."""
        return {
            "modes": ["register", "manage"],
            "elab_public_url": os.environ.get("ELAB_PUBLIC_URL", "https://elab.example.com"),
            "auth_enabled": oidc_enabled(),
            "writes_enabled": writes_enabled(),
            "beta": True,
        }

    @application.get("/api/inventory/options")
    def inventory_options() -> dict[str, Any]:
        team_id = int(os.environ.get("SCANNER_TEAM_ID", "1"))
        try:
            return load_inventory_options(_client(), team_id=team_id)
        except Exception as exc:
            raise _elab_error(exc) from exc

    @application.post("/api/scan/parse")
    def parse_scan(payload: ScanPayload) -> dict[str, Any]:
        parsed = classify_scan(payload.raw_value)
        return {
            "raw": parsed.raw,
            "symbology": parsed.symbology,
            "gtin": parsed.gtin,
            "lot": parsed.lot,
            "expiry": parsed.expiry,
            "gs1_fields": parsed.gs1_fields,
            "normalized_code": normalize_code(payload.raw_value),
        }

    @application.post("/api/catalog/lookup")
    def catalog_lookup(payload: CatalogLookupPayload) -> dict[str, Any]:
        """Local catalog lookup for scan prefill — never mutates eLabFTW."""
        cat_no = payload.catalog_number or payload.catalogue_number
        return catalog.lookup(
            code=payload.code,
            manufacturer=payload.manufacturer,
            catalog_number=cat_no,
        )

    @application.post("/api/catalog/save")
    def catalog_save(payload: CatalogSavePayload) -> dict[str, Any]:
        """Explicit operator save into the local catalog (not eLabFTW)."""
        if not payload.confirm:
            raise HTTPException(400, "Catalog save requires explicit confirmation")
        cat_no = payload.catalog_number or payload.catalogue_number
        try:
            result = catalog.save_from_manual(
                product_name=payload.product_name,
                manufacturer=payload.manufacturer,
                catalog_number=cat_no,
                cas_number=payload.cas_number,
                primary_code=payload.primary_code or "",
                alternate_codes=payload.alternate_codes,
                category_id=payload.category_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return result

    @application.get("/api/catalog/stats")
    def catalog_stats() -> dict[str, Any]:
        return {"product_count": catalog.count()}

    @application.post("/api/catalog/import/preview")
    async def catalog_import_preview(
        file: UploadFile = File(...),
        sheet: str | None = Form(default=None),
        mapping: str | None = Form(default=None),
        validate_categories: bool = Form(default=False),
    ) -> dict[str, Any]:
        """Dry-run catalog import — zero database writes."""
        try:
            data = read_upload(file.file)
            map_obj = mapping_from_form(mapping)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        known = _known_category_ids() if validate_categories else None
        try:
            preview = prepare_import(
                catalog,
                data,
                file.filename or "upload.csv",
                sheet_name=sheet or None,
                mapping=map_obj,
                known_category_ids=known,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"dry_run": True, "writes": 0, **preview.summary()}

    @application.post("/api/catalog/import/commit")
    async def catalog_import_commit(
        file: UploadFile = File(...),
        sheet: str | None = Form(default=None),
        mapping: str | None = Form(default=None),
        confirm: bool = Form(default=False),
        validate_categories: bool = Form(default=False),
    ) -> dict[str, Any]:
        """Transactional catalog import commit — requires confirm=true; never touches eLabFTW."""
        try:
            data = read_upload(file.file)
            map_obj = mapping_from_form(mapping)
            known = _known_category_ids() if validate_categories else None
            result = commit_import(
                catalog,
                data,
                file.filename or "upload.csv",
                sheet_name=sheet or None,
                mapping=map_obj,
                known_category_ids=known,
                confirm=confirm,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception:
            raise HTTPException(500, "Catalog import failed and was rolled back") from None
        return result

    @application.post("/api/catalog/import/error-report")
    async def catalog_import_error_report(
        file: UploadFile = File(...),
        sheet: str | None = Form(default=None),
        mapping: str | None = Form(default=None),
        validate_categories: bool = Form(default=False),
    ) -> Response:
        """Downloadable CSV error report for a dry-run (no DB writes)."""
        try:
            data = read_upload(file.file)
            map_obj = mapping_from_form(mapping)
            known = _known_category_ids() if validate_categories else None
            preview = prepare_import(
                catalog,
                data,
                file.filename or "upload.csv",
                sheet_name=sheet or None,
                mapping=map_obj,
                known_category_ids=known,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return PlainTextResponse(
            preview.error_report_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="catalog-import-errors.csv"'},
        )

    @application.post("/api/register/lookup")
    def register_lookup(payload: RegisterConfirmPayload) -> dict[str, Any]:
        """Lookup duplicates before create — read-only against eLabFTW."""
        try:
            client = _client()
            items = client.get("/items", limit=250)
            compounds = client.get("/compounds")
        except Exception as exc:
            raise _elab_error(exc) from exc
        mfg, cat = product_identity_key(payload.manufacturer, payload.catalogue_number)
        existing_item = match_item_exact(items, payload.manufacturer, payload.catalogue_number)
        existing_compound = None
        if payload.cas_number or payload.pubchem_cid:
            existing_compound = match_compound_exact(compounds, payload.cas_number, payload.pubchem_cid)
        from .domain import ProductCandidate, ProductIdentity

        candidate = ProductCandidate(
            identity=ProductIdentity(payload.manufacturer, payload.catalogue_number),
            product_name=payload.product_name,
            cas_number=payload.cas_number,
            pubchem_cid=payload.pubchem_cid,
        )
        conf = assess_candidate_confidence(candidate)
        return {
            "identity": {"manufacturer": mfg, "catalogue_number": cat},
            "existing_item": existing_item.__dict__ if existing_item else None,
            "existing_compound": existing_compound.__dict__ if existing_compound else None,
            "confidence": {
                "level": conf.level.value,
                "score": conf.score,
                "reasons": conf.reasons,
                "writable": conf.writable,
            },
            "requires_confirmation": True,
        }

    @application.post("/api/register/confirm")
    def register_confirm(payload: RegisterConfirmPayload, request: Request) -> dict[str, Any]:
        if not payload.manufacturer.strip() or not payload.catalogue_number.strip():
            raise HTTPException(400, "Manufacturer and catalogue number are required")
        category_id = validate_category_id(payload.category_id)
        storage_id = validate_storage_id(payload.storage_id)
        pack_lines = validate_pack_lines([line.model_dump() for line in payload.lines])
        require_writes()
        try:
            client = _client()
        except Exception as exc:
            raise _elab_error(exc) from exc
        item_id: int
        try:
            items = client.get("/items", limit=250)
        except Exception as exc:
            raise _elab_error(exc) from exc
        existing = match_item_exact(items, payload.manufacturer, payload.catalogue_number)
        if existing and existing.item_id:
            item_id = existing.item_id
            item_action = "reuse"
        else:
            try:
                item_id = client.create_item(
                    payload.product_name or f"{payload.manufacturer} {payload.catalogue_number}",
                    category_id,
                    payload.manufacturer,
                    payload.catalogue_number,
                    payload.original_barcode,
                    lot_batch=payload.lot_batch,
                    expiry_date=payload.expiry_date,
                )
            except Exception as exc:
                raise _elab_error(exc) from exc
            item_action = "create"
        compound_id = payload.compound_id
        if compound_id:
            try:
                client.link_compound(item_id, compound_id)
            except Exception as exc:
                raise _elab_error(exc) from exc
        try:
            container_specs = expand_pack_lines(pack_lines)
            created_containers: list[dict[str, Any]] = []
            public = os.environ.get("ELAB_PUBLIC_URL", "https://elab.example.com")
            for qty, unit in container_specs:
                container_id = client.create_container(item_id, storage_id, qty, unit)
                created_containers.append(
                    {
                        "id": container_id,
                        "action": "create",
                        "qty_stored": qty,
                        "qty_unit": unit,
                        "qr_url": client.container_qr_url(container_id, f"{public}/scanner"),
                    }
                )
        except Exception as exc:
            raise _elab_error(exc) from exc
        return {
            "item": {
                "id": item_id,
                "action": item_action,
                "url": f"{public}/database.php?mode=view&id={item_id}",
            },
            "containers": created_containers,
            "pack_summary": [format_pack_line(line) for line in pack_lines],
            "idempotency_key": payload.idempotency_key,
        }

    @application.get("/api/container/{container_id}")
    def get_container(container_id: int) -> dict[str, Any]:
        client = _client()
        resolved = client.find_container_by_id(container_id)
        if not resolved:
            raise HTTPException(404, "Container not found")
        c = resolved["container"]
        item = resolved["item"]
        meta = item.get("metadata")
        if isinstance(meta, str):
            import json

            meta = json.loads(meta)
        ef = extract_legacy_poc_fields(meta or {})
        return {
            "container_id": c["id"],
            "item_id": c["item_id"],
            "qty_stored": c["qty_stored"],
            "qty_unit": c["qty_unit"],
            "storage_id": c.get("storage_id"),
            "storage_name": c.get("storage_name"),
            "full_path": c.get("full_path"),
            "category_id": item.get("category"),
            "category_title": item.get("category_title"),
            "product_name": item.get("title"),
            "manufacturer": ef["manufacturer"],
            "catalogue_number": ef["catalogue_number"],
            "original_barcode": ef["original_barcode"],
            "lot_batch": ef["lot_batch"],
            "expiry_date": ef["expiry_date"],
        }

    @application.post("/api/container/{container_id}/action")
    def container_action(container_id: int, payload: ContainerActionPayload, request: Request) -> dict[str, Any]:
        require_writes()
        client = _client()
        resolved = client.find_container_by_id(container_id)
        if not resolved:
            raise HTTPException(404, "Container not found")
        c = resolved["container"]
        item_id = int(c["item_id"])
        old_qty = float(c["qty_stored"])
        unit = payload.unit or c["qty_unit"]
        new_qty = old_qty
        if payload.operation == "consume":
            if payload.qty is None:
                raise HTTPException(400, "qty required for consume")
            new_qty = old_qty - payload.qty
        elif payload.operation == "restock":
            if payload.qty is None:
                raise HTTPException(400, "qty required for restock")
            new_qty = old_qty + payload.qty
        elif payload.operation == "set_exact":
            if payload.qty is None:
                raise HTTPException(400, "qty required for set_exact")
            new_qty = payload.qty
        elif payload.operation == "mark_empty":
            new_qty = 0.0
        else:
            raise HTTPException(400, f"unknown operation {payload.operation}")
        if new_qty < 0:
            raise HTTPException(400, "quantity cannot be negative")
        client.update_container_qty(item_id, container_id, new_qty, unit)
        item = resolved["item"]
        meta = item.get("metadata")
        if isinstance(meta, str):
            import json

            meta = json.loads(meta)
        fields = _item_fields_from_payload(item)
        if any(
            v is not None
            for v in (
                payload.manufacturer,
                payload.catalogue_number,
                payload.product_name,
                payload.lot_batch,
                payload.expiry_date,
            )
        ):
            corrected = build_corrected_item_metadata(
                meta or {},
                manufacturer=payload.manufacturer if payload.manufacturer is not None else fields["manufacturer"],
                catalogue_number=payload.catalogue_number
                if payload.catalogue_number is not None
                else fields["catalogue_number"],
                lot_batch=payload.lot_batch if payload.lot_batch is not None else fields["lot_batch"],
                expiry_date=payload.expiry_date if payload.expiry_date is not None else fields["expiry_date"],
            )
            client.update_item_metadata(item_id, corrected)
            if payload.product_name and payload.product_name.strip():
                client.patch(f"/items/{item_id}", {"title": payload.product_name.strip()})
        user_id, user_email = _session_user(request)
        ledger.record(
            idempotency_key=payload.idempotency_key,
            user_id=user_id,
            user_email=user_email,
            operation=payload.operation,
            container_id=container_id,
            item_id=item_id,
            old_value={"qty_stored": old_qty, "qty_unit": c["qty_unit"]},
            new_value={"qty_stored": new_qty, "qty_unit": unit},
        )
        return {"container_id": container_id, "old_qty": old_qty, "new_qty": new_qty, "unit": unit}

    web = _web_root()
    if web.is_dir():
        application.mount("/", StaticFiles(directory=str(web), html=True), name="web")

    return application


app = create_app()

_web = _web_root()
