# Small-code mobile scanning checklist

Diagnostic mode: append `?scanner_debug=1` to the scanner URL. Reports camera label, resolution, formats, focus/zoom/torch capabilities, decoder path, and decode timing. **Does not log decoded product codes by default.**

## Device matrix

| Device / condition | Result (pass/fail) | Notes |
|--------------------|--------------------|-------|
| iPhone Safari — normal eLab QR | | |
| iPhone Safari — small printed QR | | |
| iPhone Safari — small DataMatrix | | |
| Android Chrome — normal eLab QR | | |
| Android Chrome — small printed QR | | |
| Android Chrome — small DataMatrix | | |
| Low light | | |
| Glare / reflective label | | |
| Distance ~10 cm | | |
| Distance ~20 cm | | |
| Distance ~30 cm | | |
| Zoom control (if exposed) | | |
| Torch toggle (if exposed) | | |
| Manual code entry still available | | |
| Page hidden pauses decode; resume works | | |
| Navigate away / logout releases camera | | |

## Expected graceful degradation

- No zoom/torch UI when capabilities are missing
- Continuous focus applied only when supported
- High-res ideals (1920×1080) are soft; fallback to basic environment camera
- QR_CODE and DATA_MATRIX remain enabled where the backend supports them
