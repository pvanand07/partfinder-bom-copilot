from typing import Any, Optional

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


class PriceBreak(BaseModel):
    qty: int
    price: float


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

    # Additional real DigiKey fields, surfaced as optional/hideable frontend columns.
    photoUrl: Optional[str] = None
    datasheetUrl: Optional[str] = None
    productUrl: Optional[str] = None
    series: Optional[str] = None
    leadWeeks: Optional[str] = None
    discontinued: bool = False
    endOfLife: bool = False
    ncnr: bool = False
    backOrderNotAllowed: bool = False
    reachStatus: Optional[str] = None
    moistureSensitivityLevel: Optional[str] = None
    exportControlClassNumber: Optional[str] = None
    htsusCode: Optional[str] = None
    manufacturerPublicQuantity: Optional[int] = None
    description: Optional[str] = None
    category: Optional[str] = None
    otherNames: list[str] = []
    marketplace: bool = False
    tariffActive: bool = False
    priceBreaks: list[PriceBreak] = []
    priceAt100: Optional[float] = None


class ResultBlock(BaseModel):
    keywords: str
    tags: list[str]
    matchTotal: int
    results: list[ResultRow]
    fromCache: bool = False
    cacheSource: Optional[str] = None
    cacheFresh: bool = False


class SearchRequest(BaseModel):
    query: str
    demo: bool = False


class SearchResponse(BaseModel):
    rationale: str
    blocks: list[ResultBlock]
    fromCache: bool = False
    demo: bool = False


class BatchSearchRequest(BaseModel):
    lines: list[str]
    demo: bool = False


class BatchLineResult(BaseModel):
    line: str
    qty: int
    resolved: bool
    best_row: Optional[ResultRow] = None
    fromCache: bool = False
    cacheSource: Optional[str] = None
    cacheFresh: bool = False


class BatchSearchResponse(BaseModel):
    results: list[BatchLineResult]


class RecommendCandidate(BaseModel):
    dk: str
    mpn: str
    mfr: str
    price: float
    moq: int
    stock: int
    matchScore: int
    matchNote: str
    lifecycle: str
    priceBreaks: list[PriceBreak] = []


class RecommendRequest(BaseModel):
    keywords: str
    candidates: list[RecommendCandidate]
    demo: bool = False


class Recommendation(BaseModel):
    dk: str
    recommendedQty: int
    highlight: bool
    reason: str


class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]


class BomExportLine(BaseModel):
    desig: str = ""
    qty: int = 1
    dk: str = ""
    mpn: str = ""
    mfr: str = ""
    price: float = 0
    stock: int = 0
    status: str = ""
    part: Optional[dict[str, Any]] = None


class BomExportRequest(BaseModel):
    lines: list[BomExportLine]


class ExportResultsRequest(BaseModel):
    results: list[ResultRow]
