import json
import os

from openai import OpenAI

from server.schemas import ParseResult

SYSTEM_PROMPT = """You are a parts-search query parser for an electronics BOM tool backed by the DigiKey \
catalog. Turn the user's free-text request into structured search filters. Do not search DigiKey \
yourself and do not rank parts — only extract structure.

Rules:
- Output one entry in `items` per DISTINCT part being requested. A query describing two different \
parts (e.g. "10k 0603 resistor and a 100nF 0402 cap") must produce two items, not one merged item.
- `keywords` is sent directly to DigiKey's keyword search, which is strict: it behaves like an AND of \
every word, matched against part numbers/descriptions — NOT a fuzzy full-text search. Confirmed live: \
"10k 0603 resistor" -> thousands of matches; the same query with "tape and reel" or "for a voltage \
divider" tacked on -> ZERO matches, because distributor part descriptions don't literally contain \
application-context or packaging phrasing. So `keywords` MUST be SHORT and part-description-like: just \
component type + the 2-4 most identifying specs (value, package/case size). Never include packaging \
wording ("tape and reel", "cut tape"), application context ("for a voltage divider", "no external \
diode"), or filler words — put packaging in `packaging_hint` and everything else in `attributes`, not \
in `keywords`. Also keep `keywords` plain ASCII: DigiKey's search silently returns zero results for \
the "Ω" ohm-sign symbol specifically (write "ohm" instead) — but "%", "." and other ASCII punctuation \
are fine and should be kept as-is (e.g. "1%" works; spelling it out as "1 percent" does NOT).
- Good `keywords` examples: "10k 0603 resistor", "3.3v 1a buck regulator", "usb-c receptacle smd 16 \
pin", "100nf 0402 x7r capacitor". Bad: "10k ohm 1 percent 0603 resistor tape and reel" (too many \
non-part-description words — will return zero results).
- `attributes` should list the specific parametric constraints mentioned or clearly implied (value, \
tolerance, package/case size, voltage, current, topology, etc.), each with `name` (a DigiKey-style \
parameter name such as "Resistance", "Tolerance", "Package / Case", "Voltage - Output"), `value`, and \
`unit` where applicable. Do not invent constraints that weren't stated or clearly implied.
- `qty` is the quantity requested in that item's text (e.g. "2x ..." -> 2); default to 1 if unstated.
- `search_options` may include "InStock" or "RohsCompliant" only if the user asked for that explicitly.
- `rationale` is a single short sentence (like an engineer's note) explaining any non-obvious \
interpretation choice you made. Empty string if there's nothing non-obvious to explain.
- Always respond with ONLY the JSON object matching the schema. No prose, no markdown fences.
"""

_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {"type": "string"},
        "category_hint": {"type": ["string", "null"]},
        "attributes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {"type": ["string", "null"]},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "value"],
            },
        },
        "packaging_hint": {"type": ["string", "null"]},
        "search_options": {"type": "array", "items": {"type": "string"}},
        "qty": {"type": "integer"},
    },
    "required": ["keywords", "attributes", "qty"],
}

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": _ITEM_SCHEMA},
        "rationale": {"type": "string"},
    },
    "required": ["items", "rationale"],
}


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def _call_llm(system_prompt: str, user_content: str, schema: dict, schema_name: str) -> dict:
    client = _client()
    model = os.getenv("OPENROUTER_MODEL")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        )
    except Exception:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
        )

    return _extract_json(resp.choices[0].message.content)


def parse_query(query: str) -> ParseResult:
    data = _call_llm(SYSTEM_PROMPT, f"Query: {query}", _RESPONSE_SCHEMA, "parse_result")
    return ParseResult(**data)


def parse_batch(lines: list[str]) -> ParseResult:
    numbered = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))
    prompt = (
        f"The user pasted a {len(lines)}-line BOM, one requested part per line. Produce exactly one "
        f"item in `items` per line below, in the same order (do not merge or split lines):\n{numbered}"
    )
    data = _call_llm(SYSTEM_PROMPT, prompt, _RESPONSE_SCHEMA, "parse_result")
    return ParseResult(**data)


RECOMMEND_SYSTEM_PROMPT = """You are helping an engineer decide what to actually buy, for one part search \
on an electronics BOM tool. You are given the search context and a shortlist of REAL DigiKey listings \
that already matched the search — with real price-break tiers, real MOQ, real stock, and how well each \
one matched the request (matchScore/matchNote). You are NOT searching or ranking from scratch — the \
list and its order are already decided; you are only adding a purchase quantity and pick opinion on top.

For every candidate, in the same order, decide:
- `recommendedQty`: a sensible quantity to actually order for THIS specific listing. It must be >= that \
listing's `moq` — never recommend less than the minimum order quantity. If `priceBreaks` shows a \
meaningfully cheaper tier within roughly the same order of magnitude as the MOQ (e.g. 2-5x), you may \
recommend that tier instead of the bare MOQ; do not jump to a wildly larger quantity just to chase a \
marginally lower unit price.
- `highlight`: true for the one or two listings you'd genuinely tell the engineer to buy — you may \
weigh lifecycle risk, stock depth, or price/MOQ tradeoffs differently than the existing match-based \
order, so `highlight` does not have to line up with which candidate is listed first. false for the rest.
- `reason`: one short clause (under 12 words) explaining the quantity/highlight choice for that listing.

Respond with ONLY a JSON object matching the schema — one entry in `recommendations` per candidate, \
same order, referencing each by its `dk`. No prose, no markdown fences.
"""

_RECOMMEND_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "dk": {"type": "string"},
        "recommendedQty": {"type": "integer"},
        "highlight": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["dk", "recommendedQty", "highlight", "reason"],
}

_RECOMMEND_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {"type": "array", "items": _RECOMMEND_ITEM_SCHEMA},
    },
    "required": ["recommendations"],
}


def recommend_quantities(keywords: str, candidates: list[dict]) -> list[dict]:
    """Second-pass LLM call: given the already-ranked real DigiKey candidates for one search, decide a
    purchase quantity and pick highlight per listing. Runs after the deterministic search+ranking, not
    instead of it — the LLM only ever sees candidates that already exist and are already ordered."""
    prompt = f"Search: {keywords}\nCandidates:\n{json.dumps(candidates, ensure_ascii=False)}"
    data = _call_llm(RECOMMEND_SYSTEM_PROMPT, prompt, _RECOMMEND_SCHEMA, "recommend_result")
    return data["recommendations"]
