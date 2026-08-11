# Known Limitations

- Native eLabFTW QR opens **Item**, not Container
- Container lot/expiry are not native container fields — store as Item extra fields and/or companion ledger
- OCR is not implemented (manual entry + camera barcode scan — see `docs/SCANNING_WORKFLOWS.md`)
- PubChem, if used, enriches CAS/CID only; it is not a supplier catalogue lookup
- `find_container_by_id` currently paginates Items — replace with a direct index/lookup before large scale
- Label/PDF/printer integration is out of scope for this release
- Quantity model uses floating-point values; decimal policy is not finalized
