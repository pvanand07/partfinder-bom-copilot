# Partfinder BOM Copilot

An AI-assisted DigiKey product search and BOM (bill of materials) generator.
Given a natural-language part description, an LLM extracts parametric search
filters, a FastAPI backend searches DigiKey's real Product Information v4 API
and ranks the results against those filters, and the frontend lets you build
a running BOM with real pricing, stock, and lifecycle status — export or copy
it as CSV when done.

Search is **live** — natural-language queries are parsed by an LLM (via
OpenRouter) into structured filters, then resolved against the real DigiKey
catalog (client-credentials OAuth2) with match scores computed from actual
per-part parametric data. See [docs/spec-001.md](docs/spec-001.md) for the
original design spec and [docs/issues-001.md](docs/issues-001.md) for what
was mock-only in the earlier prototype stage (most of it — #1, #2, #7 — is
now resolved).

## Contents

```
partfinder-bom-copilot/
├── README.md
├── requirements.txt        — backend Python dependencies
├── static/
│   └── bom-copilot.html    — the frontend (single-file HTML/CSS/JS)
├── server/
│   ├── main.py              — FastAPI app (/api/search, /api/batch-search)
│   ├── digikey_client.py    — DigiKey OAuth2 client-credentials + keyword search
│   ├── nl_parser.py         — OpenRouter LLM call: query -> structured filters
│   ├── ranking.py           — offline match-score computation, no LLM
│   └── schemas.py           — request/response models
├── scripts/
│   └── validate_env.py      — Phase 0 smoke test against real DigiKey + OpenRouter
├── docs/
│   ├── spec-001.md          — product & technical spec
│   └── issues-001.md        — known gaps / follow-up work
```

## Running it

1. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set `.env` (project root) with:
   ```
   DIGIKEY_CLIENT_ID=...
   DIGIKEY_CLIENT_SECRET=...
   OPENROUTER_API_KEY=...
   OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   OPENROUTER_MODEL=...
   ```
3. (Optional but recommended) sanity-check both live dependencies before
   starting the server:
   ```bash
   python scripts/validate_env.py
   ```
4. Start the backend:
   ```bash
   uvicorn server.main:app --reload --port 8000
   ```
5. Serve the frontend and open it in a browser:
   ```bash
   python3 -m http.server --directory static 8080
   # then visit http://localhost:8080/bom-copilot.html
   ```

`static/bom-copilot.html` calls the backend at `http://localhost:8000`
(`API_BASE` near the top of its `<script>`) — update that constant if you run
the backend elsewhere. DigiKey credentials and the OpenRouter API key stay
server-side in `server/`; the browser never sees them.

## What it demonstrates

- **Natural-language search** → an LLM extracts parametric filters
  (resistance, tolerance, package, packaging, etc.), a genuine DigiKey
  keyword search runs against them, and results are ranked with a match
  score computed from each part's real parametric data — shown inline with
  a collapsed "how was this interpreted" disclosure.
- **Multi-part queries** — a single query describing more than one distinct
  part (e.g. "10k 0603 resistor and a 100nF 0402 cap") renders as separate,
  independently addable result blocks instead of one merged table.
- **Genuine empty state** — an over-constrained or unsatisfiable query shows
  a real "no matches" state rather than silently falling back to unrelated
  results.
- **Paste-BOM batch mode** — resolves a multi-line pasted BOM against the
  real catalog in one pass (one LLM call for the whole batch).
- **Ranked results table** — MPN, specs, stock, unit/100-qty pricing,
  lifecycle status, and a per-row match score (`●●●○ 3/4`) explaining why a
  part ranked where it did.
- **Configurable columns** — toggle Manufacturer / MOQ columns on demand.
- **Running BOM** — quantities, line/running totals, a stock-shortfall
  warning, CSV export/copy, and a simulated 15-minute price-lock action.
  (The "Rec" designator-based quantity suggestion is still a static per-MPN
  mock — see issues-001 — since it needs a real schematic/netlist source
  this project doesn't have; it's expected to show "—" for real DigiKey
  parts.)
- **Live color tuner** — an in-UI panel (top-right, "Colors") for adjusting
  the design token palette live, with reset-to-default and copy-as-CSS.

## Status

Search, ranking, and batch resolution are live against the real DigiKey and
OpenRouter APIs — see [docs/issues-001.md](docs/issues-001.md) for what's
still mock or unfinished (CSV export is clipboard-only, no persistence
across reload, no automated tests, etc.).
