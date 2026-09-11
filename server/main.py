import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from server import nl_parser, ranking, search_cache
from server.bom_export import build_bom_workbook, build_search_results_workbook
from server.digikey_client import DigikeyClient, DigikeyError
from server.schemas import (
    BatchLineResult,
    BatchSearchRequest,
    BatchSearchResponse,
    BomExportRequest,
    ExportResultsRequest,
    ParsedItem,
    ParseResult,
    Recommendation,
    RecommendRequest,
    RecommendResponse,
    ResultBlock,
    SearchRequest,
    SearchResponse,
)

logger = logging.getLogger("partfinder")

app = FastAPI(title="DigiSearch API")

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


def _block_from_search_payload(payload: dict, cache_fresh: bool) -> ResultBlock:
    rows = search_cache.rows_from_payload(payload)
    keywords = payload.get("keywords") or ""
    tags = payload.get("tags") or []
    match_total = rows[0].matchTotal if rows else 0
    return ResultBlock(
        keywords=keywords,
        tags=tags,
        matchTotal=match_total,
        results=rows,
        fromCache=True,
        cacheSource=keywords or None,
        cacheFresh=cache_fresh,
    )


def _parse_query(query: str) -> ParseResult:
    """Fresh exact hits skip the LLM; stale/closest parse is used only if the live call fails."""
    fresh = search_cache.get_fresh_parse(query)
    if fresh is not None:
        return fresh

    try:
        parsed = nl_parser.parse_query(query)
        search_cache.put_parse(query, parsed)
        return parsed
    except Exception:
        logger.exception("nl_parser.parse_query failed")
        stale = search_cache.get_exact_parse(query) or search_cache.find_closest_parse(query)
        if stale is not None:
            return stale
        raise


def _parse_batch(lines: list[str]) -> ParseResult | None:
    fresh = search_cache.get_fresh_parse_batch(lines)
    if fresh is not None:
        return fresh

    try:
        parsed = nl_parser.parse_batch(lines)
        search_cache.put_parse_batch(lines, parsed)
        return parsed
    except Exception:
        logger.exception("nl_parser.parse_batch failed")
        return search_cache.get_exact_parse_batch(lines)


def _search_item_cached(item: ParsedItem, original_query: str, record_count: int = 25) -> tuple[list, dict]:
    """Live DigiKey unless a fresh exact cache hit exists. On failure, any-age exact then closest."""
    live_meta = {"fromCache": False, "cacheFresh": False, "cacheSource": None}

    fresh = search_cache.get_fresh_search(item.keywords)
    if fresh is not None:
        return search_cache.rows_from_payload(fresh), {
            "fromCache": True,
            "cacheFresh": True,
            "cacheSource": fresh.get("keywords") or item.keywords,
        }

    try:
        rows = _search_item(item, record_count=record_count)
        if rows:
            search_cache.put_search(item.keywords, original_query, _tags_for(item), rows)
        return rows, live_meta
    except DigikeyError:
        logger.exception("DigiKey search failed for keywords %r", item.keywords)
        payload = search_cache.get_exact_search(item.keywords)
        cache_fresh = False
        if payload is None:
            payload = search_cache.find_closest_search(item.keywords) or search_cache.find_closest_search(original_query)
        if payload is None:
            raise
        return search_cache.rows_from_payload(payload), {
            "fromCache": True,
            "cacheFresh": cache_fresh,
            "cacheSource": payload.get("keywords") or item.keywords,
        }


def _line_item_from_cache(line: str) -> ParsedItem | None:
    parsed = search_cache.get_fresh_parse(line) or search_cache.get_exact_parse(line) or search_cache.find_closest_parse(line)
    if parsed is None or not parsed.items:
        return None
    return parsed.items[0]


def _lookup_search_payload(keywords: str, original_query: str) -> tuple[dict | None, bool]:
    """Exact keywords first, then closest. Returns (payload, exact_hit)."""
    exact = search_cache.get_exact_search(keywords)
    if exact is not None:
        return exact, True
    payload = search_cache.find_closest_search(keywords) or search_cache.find_closest_search(original_query)
    return payload, False


def _search_demo(query: str) -> SearchResponse:
    """Cache-only: never call DigiKey or the LLM."""
    parsed = search_cache.get_exact_parse(query) or search_cache.find_closest_parse(query)
    if parsed is None:
        payload = search_cache.find_closest_search(query)
        if payload is None:
            return SearchResponse(rationale="", blocks=[], fromCache=False, demo=True)
        return SearchResponse(
            rationale="",
            blocks=[_block_from_search_payload(payload, cache_fresh=False)],
            fromCache=True,
            demo=True,
        )

    blocks = []
    for item in parsed.items:
        payload, exact = _lookup_search_payload(item.keywords, query)
        if payload is None:
            blocks.append(ResultBlock(
                keywords=item.keywords,
                tags=_tags_for(item),
                matchTotal=len(item.attributes),
                results=[],
            ))
            continue
        rows = search_cache.rows_from_payload(payload)
        blocks.append(ResultBlock(
            keywords=item.keywords,
            tags=_tags_for(item),
            matchTotal=len(item.attributes),
            results=rows,
            fromCache=True,
            cacheSource=payload.get("keywords") or item.keywords,
            cacheFresh=exact and search_cache.payload_is_fresh(payload),
        ))

    return SearchResponse(
        rationale=parsed.rationale,
        blocks=blocks,
        fromCache=bool(blocks) and all(b.fromCache for b in blocks),
        demo=True,
    )


def _batch_line_demo(line: str, item: ParsedItem | None) -> BatchLineResult:
    if item is None:
        item = _line_item_from_cache(line)
    if item is None:
        payload = search_cache.find_closest_search(line)
        if payload is None:
            return BatchLineResult(line=line, qty=1, resolved=False, best_row=None)
        rows = search_cache.rows_from_payload(payload)
        best_row = rows[0] if rows else None
        return BatchLineResult(
            line=line,
            qty=1,
            resolved=best_row is not None,
            best_row=best_row,
            fromCache=True,
            cacheSource=payload.get("keywords"),
            cacheFresh=False,
        )

    payload, exact = _lookup_search_payload(item.keywords, line)
    if payload is None:
        return BatchLineResult(line=line, qty=item.qty, resolved=False, best_row=None)
    rows = search_cache.rows_from_payload(payload)
    best_row = rows[0] if rows else None
    return BatchLineResult(
        line=line,
        qty=item.qty,
        resolved=best_row is not None,
        best_row=best_row,
        fromCache=True,
        cacheSource=payload.get("keywords") or item.keywords,
        cacheFresh=exact and search_cache.payload_is_fresh(payload),
    )


def _recommend_cached_only(req: RecommendRequest) -> list[dict]:
    dks = [c.dk for c in req.candidates]
    return (
        search_cache.get_exact_recommend(req.keywords, dks)
        or search_cache.find_recommend_for_keywords(req.keywords, dks)
        or search_cache.find_closest_recommend(req.keywords, dks)
        or []
    )


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest):
    if req.demo:
        return _search_demo(req.query)

    try:
        parsed = _parse_query(req.query)
    except Exception as exc:
        payload = search_cache.find_closest_search(req.query)
        if payload is None:
            raise HTTPException(status_code=502, detail=f"Query parsing failed: {exc}") from exc
        block = _block_from_search_payload(payload, cache_fresh=False)
        return SearchResponse(rationale="", blocks=[block], fromCache=True)

    blocks = []
    for item in parsed.items:
        try:
            rows, meta = _search_item_cached(item, req.query)
        except DigikeyError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        blocks.append(ResultBlock(
            keywords=item.keywords,
            tags=_tags_for(item),
            matchTotal=len(item.attributes),
            results=rows,
            fromCache=meta["fromCache"],
            cacheSource=meta["cacheSource"],
            cacheFresh=meta["cacheFresh"],
        ))

    return SearchResponse(
        rationale=parsed.rationale,
        blocks=blocks,
        fromCache=bool(blocks) and all(b.fromCache for b in blocks),
    )


@app.post("/api/batch-search", response_model=BatchSearchResponse)
def batch_search(req: BatchSearchRequest):
    lines = [l for l in req.lines if l.strip()]
    if not lines:
        return BatchSearchResponse(results=[])

    if req.demo:
        parsed = search_cache.get_exact_parse_batch(lines)
        results = []
        for i, line in enumerate(lines):
            item = parsed.items[i] if parsed is not None and i < len(parsed.items) else None
            results.append(_batch_line_demo(line, item))
        return BatchSearchResponse(results=results)

    parsed = _parse_batch(lines)

    results = []
    for i, line in enumerate(lines):
        item = parsed.items[i] if parsed is not None and i < len(parsed.items) else None
        if item is None:
            item = _line_item_from_cache(line)

        if item is None:
            payload = search_cache.find_closest_search(line)
            if payload is None:
                results.append(BatchLineResult(line=line, qty=1, resolved=False, best_row=None))
                continue
            rows = search_cache.rows_from_payload(payload)
            best_row = rows[0] if rows else None
            results.append(BatchLineResult(
                line=line,
                qty=1,
                resolved=best_row is not None,
                best_row=best_row,
                fromCache=True,
                cacheSource=payload.get("keywords"),
                cacheFresh=False,
            ))
            continue

        try:
            rows, meta = _search_item_cached(item, line, record_count=10)
        except DigikeyError:
            results.append(BatchLineResult(line=line, qty=item.qty, resolved=False, best_row=None))
            continue

        best_row = rows[0] if rows else None
        results.append(BatchLineResult(
            line=line,
            qty=item.qty,
            resolved=best_row is not None,
            best_row=best_row,
            fromCache=meta["fromCache"],
            cacheSource=meta["cacheSource"],
            cacheFresh=meta["cacheFresh"],
        ))

    return BatchSearchResponse(results=results)


def _recommendations_from_raw(req: RecommendRequest, raw: list[dict]) -> list[Recommendation]:
    by_dk = {r["dk"]: r for r in raw if "dk" in r}
    recommendations = []
    for c in req.candidates:
        r = by_dk.get(c.dk)
        if r:
            recommendations.append(Recommendation(
                dk=c.dk, recommendedQty=r.get("recommendedQty", c.moq),
                highlight=bool(r.get("highlight")), reason=r.get("reason", ""),
            ))
        else:
            recommendations.append(Recommendation(dk=c.dk, recommendedQty=c.moq, highlight=False, reason=""))
    return recommendations


@app.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    if not req.candidates:
        return RecommendResponse(recommendations=[])

    candidates = [c.model_dump() for c in req.candidates]
    dks = [c.dk for c in req.candidates]

    if req.demo:
        return RecommendResponse(recommendations=_recommendations_from_raw(req, _recommend_cached_only(req)))

    fresh = search_cache.get_fresh_recommend(req.keywords, dks)
    if fresh is not None:
        return RecommendResponse(recommendations=_recommendations_from_raw(req, fresh))

    try:
        raw = nl_parser.recommend_quantities(req.keywords, candidates)
        search_cache.put_recommend(req.keywords, dks, raw)
    except Exception as exc:
        logger.exception("nl_parser.recommend_quantities failed")
        raw = search_cache.get_exact_recommend(req.keywords, dks)
        if raw is None:
            raw = search_cache.find_recommend_for_keywords(req.keywords, dks)
        if raw is None:
            raise HTTPException(status_code=502, detail=f"Recommendation failed: {exc}") from exc

    return RecommendResponse(recommendations=_recommendations_from_raw(req, raw))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/export-bom")
def export_bom(req: BomExportRequest):
    if not req.lines:
        raise HTTPException(status_code=400, detail="BOM is empty")
    data = build_bom_workbook([line.model_dump() for line in req.lines])
    filename = f"DigiSearch-BOM-{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/export-results")
def export_results(req: ExportResultsRequest):
    if not req.results:
        raise HTTPException(status_code=400, detail="No search results to export")
    data = build_search_results_workbook([row.model_dump() for row in req.results])
    filename = f"DigiSearch-Results-{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
def index():
    return RedirectResponse(url="/bom-copilot.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
