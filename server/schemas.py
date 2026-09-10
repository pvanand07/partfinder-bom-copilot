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
