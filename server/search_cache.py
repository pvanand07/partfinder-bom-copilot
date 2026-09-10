"""Permanent disk cache for DigiKey searches and LLM parse/recommend results.

Entries never expire. A 30-day freshness window is a read policy: younger exact
hits skip the live call; older entries stay on disk for failure fallback.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Iterable, Optional

from diskcache import Cache

from server.schemas import ParseResult, ResultRow

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "search-cache"
MAX_AGE = timedelta(days=30)
MIN_RATIO = 0.35

PREFIX_PARSE = "parse:"
PREFIX_PARSE_BATCH = "parse_batch:"
PREFIX_SEARCH = "search:"
PREFIX_RECOMMEND = "recommend:"

_TOKEN_RE = re.compile(r"[a-z0-9%]+")

_cache = Cache(str(CACHE_DIR))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_cached_at(payload: dict) -> Optional[datetime]:
    raw = payload.get("cached_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_fresh(payload: dict, max_age: timedelta = MAX_AGE) -> bool:
    cached_at = _parse_cached_at(payload)
    if cached_at is None:
        return False
    return datetime.now(timezone.utc) - cached_at < max_age


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _batch_key(lines: Iterable[str]) -> str:
    return "\n".join(_normalize(line) for line in lines)


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _score(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    q_tokens = _tokenize(query)
    c_tokens = _tokenize(candidate)
    if not q_tokens or not c_tokens:
        return 0.0
    overlap = len(q_tokens & c_tokens)
    if overlap == 0:
        return 0.0
    jaccard = overlap / len(q_tokens | c_tokens)
    coverage = overlap / len(q_tokens)
    seq = SequenceMatcher(None, query.lower(), candidate.lower()).ratio()
    return 0.5 * coverage + 0.3 * jaccard + 0.2 * seq


def _get(key: str) -> Optional[dict]:
    payload = _cache.get(key)
    return payload if isinstance(payload, dict) else None


def _put(key: str, payload: dict) -> None:
    _cache.set(key, payload, expire=None)


def _iter_prefix(prefix: str) -> Iterable[tuple[str, dict]]:
    for key in list(_cache):
        if isinstance(key, str) and key.startswith(prefix):
            payload = _get(key)
            if payload is not None:
                yield key, payload


def _best_scored(query: str, candidates: Iterable[tuple[str, dict, Iterable[str]]]) -> Optional[dict]:
    best_payload = None
    best_score = 0.0
    for _key, payload, texts in candidates:
        score = max((_score(query, text) for text in texts), default=0.0)
        if score > best_score:
            best_score = score
            best_payload = payload
    if best_payload is None or best_score < MIN_RATIO:
        return None
    return best_payload


def _parse_result(payload: dict) -> ParseResult:
    return ParseResult(
        items=payload.get("items") or [],
        rationale=payload.get("rationale") or "",
    )


def rows_from_payload(payload: dict) -> list[ResultRow]:
    rows = []
    for raw in payload.get("rows") or []:
        try:
            rows.append(ResultRow(**raw))
        except Exception:
            continue
    return rows


# --- parse (single query) -------------------------------------------------


def put_parse(query: str, parsed: ParseResult) -> None:
    dumped = parsed.model_dump()
    dumped["original_query"] = query
    dumped["cached_at"] = _now_iso()
    _put(PREFIX_PARSE + _normalize(query), dumped)


def get_fresh_parse(query: str) -> Optional[ParseResult]:
    payload = _get(PREFIX_PARSE + _normalize(query))
    if payload and _is_fresh(payload):
        return _parse_result(payload)
    return None


def get_exact_parse(query: str) -> Optional[ParseResult]:
    payload = _get(PREFIX_PARSE + _normalize(query))
    return _parse_result(payload) if payload else None


def find_closest_parse(query: str) -> Optional[ParseResult]:
    payload = _best_scored(query, (
        (key, data, (data.get("original_query") or "", key[len(PREFIX_PARSE):]))
        for key, data in _iter_prefix(PREFIX_PARSE)
    ))
    return _parse_result(payload) if payload else None


# --- parse (batch) ----------------------------------------------------------


def put_parse_batch(lines: list[str], parsed: ParseResult) -> None:
    dumped = parsed.model_dump()
    dumped["original_query"] = "\n".join(lines)
    dumped["cached_at"] = _now_iso()
    _put(PREFIX_PARSE_BATCH + _batch_key(lines), dumped)


def get_fresh_parse_batch(lines: list[str]) -> Optional[ParseResult]:
    payload = _get(PREFIX_PARSE_BATCH + _batch_key(lines))
    if payload and _is_fresh(payload):
        return _parse_result(payload)
    return None


def get_exact_parse_batch(lines: list[str]) -> Optional[ParseResult]:
    payload = _get(PREFIX_PARSE_BATCH + _batch_key(lines))
    return _parse_result(payload) if payload else None


# --- DigiKey search ----------------------------------------------------------


def put_search(keywords: str, original_query: str, tags: list[str], rows: list[ResultRow]) -> None:
    if not rows:
        return
    _put(PREFIX_SEARCH + _normalize(keywords), {
        "keywords": keywords,
        "original_query": original_query,
        "tags": tags,
        "rows": [r.model_dump() for r in rows],
        "cached_at": _now_iso(),
    })


def get_fresh_search(keywords: str) -> Optional[dict]:
    payload = _get(PREFIX_SEARCH + _normalize(keywords))
    if payload and _is_fresh(payload):
        return payload
    return None


def get_exact_search(keywords: str) -> Optional[dict]:
    return _get(PREFIX_SEARCH + _normalize(keywords))


def find_closest_search(query: str) -> Optional[dict]:
    return _best_scored(query, (
        (
            key,
            data,
            (
                data.get("keywords") or "",
                data.get("original_query") or "",
                key[len(PREFIX_SEARCH):],
            ),
        )
        for key, data in _iter_prefix(PREFIX_SEARCH)
    ))


# --- recommend ------------------------------------------------------------


def _recommend_key(keywords: str, dks: Iterable[str]) -> str:
    dk_part = ",".join(sorted(dk for dk in dks if dk))
    return PREFIX_RECOMMEND + _normalize(keywords) + "|" + dk_part


def put_recommend(keywords: str, dks: Iterable[str], recommendations: list[dict]) -> None:
    _put(_recommend_key(keywords, dks), {
        "keywords": keywords,
        "recommendations": recommendations,
        "cached_at": _now_iso(),
    })


def get_fresh_recommend(keywords: str, dks: Iterable[str]) -> Optional[list[dict]]:
    payload = _get(_recommend_key(keywords, dks))
    if payload and _is_fresh(payload):
        return payload.get("recommendations") or []
    return None


def get_exact_recommend(keywords: str, dks: Iterable[str]) -> Optional[list[dict]]:
    payload = _get(_recommend_key(keywords, dks))
    return (payload.get("recommendations") or []) if payload else None


def find_recommend_for_keywords(keywords: str, dks: Iterable[str]) -> Optional[list[dict]]:
    wanted = {dk for dk in dks if dk}
    prefix = PREFIX_RECOMMEND + _normalize(keywords) + "|"
    best_recs: Optional[list[dict]] = None
    best_overlap = -1
    for key, payload in _iter_prefix(prefix):
        recs = payload.get("recommendations") or []
        rec_dks = {r.get("dk") for r in recs if r.get("dk")}
        overlap = len(rec_dks & wanted)
        if overlap > best_overlap:
            best_overlap = overlap
            best_recs = recs
    return best_recs


def find_closest_recommend(keywords: str, dks: Iterable[str]) -> Optional[list[dict]]:
    same = find_recommend_for_keywords(keywords, dks)
    if same:
        return same

    wanted = {dk for dk in dks if dk}
    best_recs: Optional[list[dict]] = None
    best_score = 0.0
    for key, payload in _iter_prefix(PREFIX_RECOMMEND):
        rec_keywords = payload.get("keywords") or ""
        if not rec_keywords and "|" in key[len(PREFIX_RECOMMEND):]:
            rec_keywords = key[len(PREFIX_RECOMMEND):].split("|", 1)[0]
        recs = payload.get("recommendations") or []
        rec_dks = {r.get("dk") for r in recs if r.get("dk")}
        overlap = len(rec_dks & wanted)
        score = _score(keywords, rec_keywords) + (0.15 if overlap else 0.0)
        if score > best_score:
            best_score = score
            best_recs = recs
    if best_recs is None or best_score < MIN_RATIO:
        return None
    return best_recs


def payload_is_fresh(payload: dict) -> bool:
    return _is_fresh(payload)
