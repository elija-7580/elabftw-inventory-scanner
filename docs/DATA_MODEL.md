# Data Model

Authoritative: **Compound → Item → Container**

See also `ELABFTW_DATA_MODEL.md` (project root, historical).

- **Compound** — chemical identity (CAS, PubChem CID)
- **Item** — supplier product; `compounds_links` when valid
- **Container** — physical package; `qty_stored`, `qty_unit`, `storage_id`
- **Ledger** (companion) — audit events only; FK to container_id
