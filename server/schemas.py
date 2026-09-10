from typing import Optional

from pydantic import BaseModel


class ExtractedAttribute(BaseModel):
    name: str
    value: str
    unit: Optional[str] = None
    aliases: list[str] = []


class ParsedItem(BaseModel):
    keywords: str
    category_hint: Optional[str] = None
    attributes: list[ExtractedAttribute] = []
    packaging_hint: Optional[str] = None
    search_options: list[str] = []
    qty: int = 1


class ParseResult(BaseModel):
    items: list[ParsedItem]
    rationale: str = ""


class Alternate(BaseModel):
    mpn: str
    why: str


class ResultRow(BaseModel):
    dk: str
    mfr: str
    mpn: str
    attrs: str
    stock: int
    status: str  # "in" | "low" | "out"
    price: float
    moq: int
    best: bool
    rohs: bool
    lifecycle: str
    matchScore: int
    matchTotal: int
    matchNote: str
    alts: list[Alternate] = []


class ResultBlock(BaseModel):
    keywords: str
    tags: list[str]
    matchTotal: int
    results: list[ResultRow]


class SearchRequest(BaseModel):
    query: str


class SearchResponse(BaseModel):
    rationale: str
    blocks: list[ResultBlock]


class BatchSearchRequest(BaseModel):
    lines: list[str]


class BatchLineResult(BaseModel):
    line: str
    qty: int
    resolved: bool
    best_row: Optional[ResultRow] = None


class BatchSearchResponse(BaseModel):
    results: list[BatchLineResult]
