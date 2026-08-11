# eLabFTW inventory data model notes

Authoritative inventory chain in eLabFTW:

**Compound → Item → Container**

| Entity | Role |
|---|---|
| Compound | Chemical identity (CAS, PubChem CID) |
| Item | Supplier / product record; optional `compounds_links` |
| Container | Physical package with `qty_stored`, `qty_unit`, `storage_id` |
| storage_units | Authoritative location hierarchy |

## Companion ledger

Native eLabFTW provides **current quantity patch**, not append-only semantic transactions.

This scanner keeps a companion SQLite ledger for:

- consumption, addition, correction, disposal, receiving (as implemented)
- idempotency keys
- user attribution snapshots

Store **foreign keys only** (`compound_id`, `item_id`, `container_id`, `user_id`, `experiment_id`).

## Location taxonomy (template)

Use `config/location_hierarchy.template.yaml` as a planning template only.
Do **not** invent production rooms/cabinets in automation — operators maintain eLabFTW `storage_units`.

Example placeholder tree:

```
Building
  └── Unassigned Location
```
