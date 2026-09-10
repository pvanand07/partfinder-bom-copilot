# Spec 001 — Partfinder BOM Copilot

Status: **Draft** · Scope: UI prototype, `static/bom-copilot.html`

## 1. Problem

Engineers building a BOM against DigiKey's catalog today move between free-text
search, manually reading parametric filters, and copy-pasting part numbers
into a spreadsheet. Partfinder collapses that into one flow:

```
Natural-language query → interpreted filters → ranked results → BOM → export
```

## 2. Users & primary task

A hardware engineer or procurement person assembling a BOM for a board
(e.g. "ESP32 Weather Node rev C"), who wants to go from "I need a 10k 0603
resistor" to a priced, stock-checked line item with minimal manual lookup.

## 3. Functional scope (implemented in the prototype)

### 3.1 Search
- Single natural-language query input, plus four example queries.
- Query is matched against a fixed set of canned interpretations (mock —
  see §6). Each interpretation exposes:
  - A short list of extracted filter values (`10kΩ`, `±1%`, `0603`, …).
  - A one-line rationale, collapsed behind "How was this interpreted?".

### 3.2 Paste-BOM batch mode
- A textarea accepting one part request per line, with an optional
  leading quantity (`2x 10k 0603 1% resistor …`).
- Each line is resolved against the same canned-query matcher used by
  single search, defaulting to qty 1 when no quantity prefix is given.
- Resolved lines are added to the BOM in one action; unresolved lines are
  counted and reported but not added.

### 3.3 Results table
Columns (left→right, all optional ones off by default):
`Part (MPN + mfr/DK#/datasheet link + match score + alternates) | [Manufacturer] | Specs | Stock | [MOQ] | Unit price | Price @ qty 100 | Lifecycle | Add`

- **Best fit** row is marked with a left accent border + a ★ next to the MPN.
- **Match score** (`●●●○ 3/4`) is shown per row against a fixed
  `matchTotal` for the active query, with the specific mismatch reason in
  a hover tooltip (native `title`).
- **Stock** status drives color only on the exception cases: low stock and
  out-of-stock get colored text + a short note (lead time for out-of-stock);
  in-stock is plain text.
- **Lifecycle**: `Active` is plain muted text; `NRND` is bold amber.
- **Alternates**: an expandable inline list of substitute parts with a
  one-line reason each (only populated on one example row).
- **Sort**: Best fit / Unit price / Stock.
- **Columns menu**: toggles the optional Manufacturer and MOQ columns,
  reflowing the grid via a CSS custom property (`--cols`) rather than
  fixed markup.

### 3.4 BOM panel
- Line list: MPN, manufacturer, unit price, designator string, qty
  stepper (±1, min 1), line total, remove.
- Summary: line count, total units, estimated cost, a stock-shortfall
  warning when a line's requested qty exceeds mock stock.
- Actions: **Export CSV** (copies CSV to clipboard — see §5), **Copy**
  (same CSV to clipboard), **Lock pricing (15 min)** (cosmetic — sets a
  simulated expiry time, no real quote object).

### 3.5 Color tuner
- A panel (toggled from the header) exposing 12 CSS custom properties
  (surfaces, text, accent, semantic status colors) as paired
  swatch + hex inputs.
- Changes apply live via `documentElement.style.setProperty`.
- Persisted to `localStorage` (`bom-copilot-colors`) so they survive a
  reload in the same browser.
- **Reset to default** and **Copy CSS** (copies a `:root{...}` block of
  current values) actions.

## 4. Non-functional / design constraints

- **Single-file artifact**: no build step, no bundler. Fonts load from
  Google Fonts; everything else is inline.
- **Single theme**: committed to a light theme only (no dark mode) — see
  design history in this doc's changelog for why.
- **Design tokens**: all color, radius, and shadow values are CSS custom
  properties on `:root`, consumed by every component — this is what makes
  the color tuner possible.
- **Outer-panel treatment**: the three top-level panels (search block,
  results table, BOM sidebar) use square corners and a dark border
  (`--line-strong`); everything nested inside them uses the normal
  rounded / light-hairline treatment.
- **Density over decoration**: no large explanatory panels; AI reasoning
  is hidden behind disclosures/tooltips rather than shown inline by
  default.

## 5. Data & integration model (not implemented — mock only)

The prototype's `CATALOG` object simulates what would come from three real
DigiKey Product Information v4 / Quote v4 endpoints:

| Prototype concept | Real endpoint (DigiKey API) |
|---|---|
| Search results | `KeywordSearch` |
| Per-part detail (stock, pricing, lifecycle, RoHS) | `ProductDetails` / `ProductPricing` / `PricingOptionsByQuantity` |
| Alternates | `Substitutions`, `RecommendedProducts` |
| "Lock pricing" | `Quote v4` (batch price + time-boxed quote lock) |
| Manufacturer/category filters | `Manufacturers`, `Categories` |

Auth model for a real integration: OAuth 2.0 client-credentials (2-legged)
for search/pricing; a production app would also need a rate-limit budget
display sourced from the real `X-RateLimit-Remaining` header rather than
the static figure that previously appeared in this prototype (removed —
see issues log).

CSV export currently works by copying CSV text to the clipboard (browser
sandbox blocks programmatic file downloads from this artifact); a real
deployment would offer an actual file download.

## 6. Known simplifications

- Search is not real NLP — it's a fixed lookup table of five canned
  queries (`CATALOG` / `INTERP` keyed by exact query string), each with
  hand-authored "best fit" ranking and match scores.
- Designator assignment (`R1, R2`, `C1–C6`, …) is a static per-MPN map,
  not derived from an actual schematic/netlist.
- All catalog data is fabricated but DigiKey-plausible (real manufacturer
  names, plausible part-number formats) — explicitly labeled as sample
  data in the UI footer.

See [issues-001.md](issues-001.md) for the prioritized list of gaps.
