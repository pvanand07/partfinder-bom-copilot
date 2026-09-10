# Issues 001 — Partfinder BOM Copilot

Tracking known gaps in `static/bom-copilot.html` against
[spec-001.md](spec-001.md). Prototype-stage issues — none of these are bugs
in the sense of "breaks the demo," they're gaps between the prototype and a
shippable product.

| # | Title | Area | Priority |
|---|---|---|---|
| 1 | No real search — fixed 5-query lookup table | Search | High |
| 2 | Unmatched query silently falls back to the first catalog | Search | High |
| 3 | Batch-mode line matching is a fragile keyword heuristic | Batch | Medium |
| 4 | CSV "export" only copies to clipboard, no file download | BOM | Medium |
| 5 | BOM state is not persisted across reload | BOM | Medium |
| 6 | Alternates populated on only one row in the sample data | Results | Low |
| 7 | Match score / mismatch reasons are hand-authored, not computed | Results | Medium |
| 8 | Specs column is unstructured text, no per-attribute columns | Results | Low |
| 9 | No accessibility pass on custom controls | A11y | Medium |
| 10 | Dense 7–9 column table has no real mobile layout | Responsive | Medium |
| 11 | Color tuner has no contrast guard | Color tuner | Low |
| 12 | "Lock pricing" and rate-limit indicator are cosmetic only | BOM / Header | Low |
| 13 | No automated tests | Tooling | Low |

---

## 1. No real search — fixed 5-query lookup table
**Area:** Search · **Priority:** High

`CATALOG` and `INTERP` are keyed by five exact query strings. There is no
actual parsing — `runSearch()` does `CATALOG[q] ? q : Object.keys(CATALOG)[0]`.
Typing anything other than one of the five example queries verbatim (or via
the example pills) returns the first catalog category.

**Fix:** replace with a real `KeywordSearch` call against the DigiKey API,
or at minimum a fuzzy-match layer over a larger local catalog before this
goes anywhere near real users.

## 2. Unmatched query silently falls back, no "no results" state
**Area:** Search · **Priority:** High

Related to #1 — because of the fallback, the UI can never show "no matches
found," which is a real and important state for a parametric search tool
(e.g. an over-constrained query). There's currently no UI for it at all.

**Fix:** add an empty-state row/panel, and stop silently substituting a
different category's results.

## 3. Batch-mode line matching is a fragile keyword heuristic
**Area:** Batch · **Priority:** Medium

`runBatch()` matches each pasted line against catalog keys via
`includes()` on the first few words, then a fallback of "any word >2 chars
appears in the key." This will misfire easily on real free-text BOMs (e.g.
two categories sharing a word like "cap" or "diode").

**Fix:** needs the same real search backend as #1; heuristic string
matching won't scale past the demo's five categories.

## 4. CSV "export" only copies to clipboard
**Area:** BOM · **Priority:** Medium

`exportCsv()` calls `copyList()` — there is no `<a download>` or file save,
because the artifact sandbox blocks script-driven downloads. This is a
correct workaround for this environment but not the real product
behavior.

**Fix:** in a real deployment (not this artifact host), wire this to an
actual file download or a "send to spreadsheet" integration.

## 5. BOM state is not persisted across reload
**Area:** BOM · **Priority:** Medium

`bom` is an in-memory array only. Reloading the page loses the BOM
entirely. (The color tuner *does* persist, via `localStorage` — the BOM
does not, which is an inconsistency worth resolving one way or the
other.)

**Fix:** persist `bom` to `localStorage` (prototype-appropriate) or to a
real backend (product-appropriate), matching whatever the color tuner
already does for consistency.

## 6. Alternates populated on only one row in the sample data
**Area:** Results · **Priority:** Low

Only the top resistor result (`RC0603FR-0710KL`) has an `alts` array; every
other row across all five categories has none, so the "+N alternates"
disclosure is only demonstrable on one query.

**Fix:** either populate more sample rows for a fuller demo, or accept
this as intentionally minimal for a prototype.

## 7. Match score / mismatch reasons are hand-authored, not computed
**Area:** Results · **Priority:** Medium

Each catalog row carries a manually written `matchScore`/`matchTotal`/
`matchNote`. This is fine for a fixed demo but doesn't generalize — a real
implementation needs the match score computed from an actual comparison
between parsed query constraints and each part's real parametric data.

**Fix:** define the constraint-matching algorithm as part of the real
search integration (see #1); this is the mechanism that makes "AI value
through transparent ranking" actually true rather than scripted.

## 8. Specs column is unstructured text, no per-attribute columns
**Area:** Results · **Priority:** Low

The `attrs` field is a single joined string (`"10kΩ · ±1% · 0603 · 100mW"`)
rather than structured fields. Per-attribute columns (value, tolerance,
package, voltage, etc.) would require a category-specific schema, since a
resistor's attributes aren't a regulator's. Deferred as a larger structural
change — noted during design review, not started.

**Fix:** design a category-aware attribute schema before attempting
per-attribute columns; don't bolt this onto the current flat `attrs`
string.

## 9. No accessibility pass on custom controls
**Area:** A11y · **Priority:** Medium

The columns menu, alternates disclosure, and why/about panels are custom
show/hide widgets without ARIA state (`aria-expanded`, `aria-controls`,
etc.) or documented keyboard interaction beyond native button/input
focus. Explicitly out of scope during the design pass, but should be
addressed before any real ship.

**Fix:** add ARIA attributes and verify keyboard operability (Escape to
close popovers, focus return on close, etc.).

## 10. Dense table has no real mobile layout
**Area:** Responsive · **Priority:** Medium

Below 900px the two-column grid collapses to one column, but the results
table itself (7–9 grid columns depending on toggled columns) only gets
`overflow-x:auto` — it hasn't been tested on an actual small viewport, and
a 7-column dense table is a poor fit for mobile regardless.

**Fix:** design a distinct compact/card layout for the results list under
some breakpoint, rather than relying on horizontal scroll alone.

## 11. Color tuner has no contrast guard
**Area:** Color tuner · **Priority:** Low

`--accent-ink` (text-on-accent color) is fixed white and not exposed in
the tuner. Picking a light `--accent` value (e.g. pale yellow) produces
low-contrast button text with no warning.

**Fix:** either expose `--accent-ink` as a 13th tunable, or compute a
contrast-appropriate ink color automatically when `--accent` changes.

## 12. "Lock pricing" and rate-limit indicator are cosmetic only
**Area:** BOM / Header · **Priority:** Low

`lockQuote()` sets a `Date.now() + 15min` label with no real expiry
enforcement or backing quote object. The header's request-quota badge
was removed earlier in the design process as decorative/prototype noise
(see spec-001 §4) — the remaining "Lock pricing" affordance has the same
character and should get the same treatment (real backend, or removed)
before shipping.

## 13. No automated tests
**Area:** Tooling · **Priority:** Low

Single HTML file, no test harness. Fine for a design prototype; would
need real test coverage (at minimum for the batch-line parser and CSV
builder) before being trusted in a real product.
