# Partfinder BOM Copilot

A UI prototype for an AI-assisted DigiKey product search and BOM (bill of
materials) generator. Given a natural-language part description, it maps the
request to parametric filters, ranks catalog matches against those filters,
and lets you build a running BOM with pricing, stock, and lifecycle status —
export or copy it as CSV when done.

This is a **frontend prototype with mock data** — no live DigiKey API calls
are made. See [docs/spec-001.md](docs/spec-001.md) for the intended real
integration.

## Contents

```
partfinder-bom-copilot/
├── README.md
├── static/
│   └── bom-copilot.html   — the prototype (single-file HTML/CSS/JS)
├── docs/
│   ├── spec-001.md        — product & technical spec
│   └── issues-001.md      — known gaps / follow-up work
```

## Running it

The prototype is a single self-contained HTML file with no build step and no
external services required (fonts load from Google Fonts over CDN; there are
no other dependencies).

Open it directly in a browser:

```bash
open static/bom-copilot.html      # macOS
start static/bom-copilot.html     # Windows
```

Or serve it locally:

```bash
python3 -m http.server --directory static 8080
# then visit http://localhost:8080/bom-copilot.html
```

## What it demonstrates

- **Natural-language search** → parsed into parametric filters (resistance,
  tolerance, package, packaging, etc.), shown inline with a collapsed
  "how was this interpreted" disclosure.
- **Paste-BOM batch mode** — resolve a multi-line pasted BOM against the
  catalog in one pass.
- **Ranked results table** — MPN, specs, stock, unit/100-qty pricing,
  lifecycle status, and a per-row match score (`●●●○ 3/4`) explaining why a
  part ranked where it did.
- **Configurable columns** — toggle Manufacturer / MOQ columns on demand.
- **Running BOM** — quantities, designators, line/running totals, a
  stock-shortfall warning, CSV export/copy, and a simulated 15-minute
  price-lock action.
- **Live color tuner** — an in-UI panel (top-right, "Colors") for adjusting
  the design token palette live, with reset-to-default and copy-as-CSS.

## Status

Prototype / design exploration. Not connected to any backend or the real
DigiKey API. See [docs/issues-001.md](docs/issues-001.md) for what's missing
before this could ship.
