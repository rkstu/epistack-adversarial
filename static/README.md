# static — Shared Assets

## `style.css`

CSS stylesheet used by all generated HTML output pages. 150 lines covering:
- Position cards with color-coding (blue=zoonotic, red=lab-leak, purple=methodology)
- Confidence bars (green/yellow/red fill)
- Edge-type badges (supports, contradicts, frames_differently)
- Settling alerts (warning/success)
- Crux score display
- Responsive layout

Inspired by daisyUI/Tabler card patterns. Zero framework dependencies — pure CSS.

This file is copied into each `output/<case>/static/` directory during site generation by `generate_site.py`.
