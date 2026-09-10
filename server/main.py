import logging

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from server import nl_parser, ranking
from server.digikey_client import DigikeyClient, DigikeyError
from server.schemas import (
    BatchLineResult,
    BatchSearchRequest,
    BatchSearchResponse,
    ParsedItem,
    ResultBlock,
    SearchRequest,
    SearchResponse,
)

logger = logging.getLogger("partfinder")

app = FastAPI(title="Partfinder BOM Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_digikey = DigikeyClient()


def _search_item(item: ParsedItem, record_count: int = 25) -> list:
    response = _digikey.keyword_search(item.keywords, item.search_options, record_count=record_count)
    products = response.get("Products", [])
    return ranking.flatten_products(products, item.attributes)


def _tags_for(item: ParsedItem) -> list[str]:
    return [f"{a.value}{a.unit or ''}".strip() for a in item.attributes]


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest):
    try:
        parsed = nl_parser.parse_query(req.query)
    except Exception as exc:
        logger.exception("nl_parser.parse_query failed")
        raise HTTPException(status_code=502, detail=f"Query parsing failed: {exc}") from exc

    blocks = []
    for item in parsed.items:
        try:
            rows = _search_item(item)
        except DigikeyError as exc:
            logger.exception("DigiKey search failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        blocks.append(ResultBlock(
            keywords=item.keywords,
            tags=_tags_for(item),
            matchTotal=len(item.attributes),
            results=rows,
        ))

    return SearchResponse(rationale=parsed.rationale, blocks=blocks)


@app.post("/api/batch-search", response_model=BatchSearchResponse)
def batch_search(req: BatchSearchRequest):
    lines = [l for l in req.lines if l.strip()]
    if not lines:
        return BatchSearchResponse(results=[])

    try:
        parsed = nl_parser.parse_batch(lines)
    except Exception as exc:
        logger.exception("nl_parser.parse_batch failed")
        raise HTTPException(status_code=502, detail=f"Batch parsing failed: {exc}") from exc

    results = []
    for i, line in enumerate(lines):
        item = parsed.items[i] if i < len(parsed.items) else None
        if item is None:
            results.append(BatchLineResult(line=line, qty=1, resolved=False, best_row=None))
            continue

        try:
            rows = _search_item(item, record_count=10)
        except DigikeyError as exc:
            logger.exception("DigiKey search failed for batch line %r", line)
            results.append(BatchLineResult(line=line, qty=item.qty, resolved=False, best_row=None))
            continue

        best_row = rows[0] if rows else None
        results.append(BatchLineResult(line=line, qty=item.qty, resolved=best_row is not None, best_row=best_row))

    return BatchSearchResponse(results=results)


@app.get("/api/health")
def health():
    return {"status": "ok"}
