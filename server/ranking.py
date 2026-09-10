import re

from server.schemas import Alternate, ExtractedAttribute, PriceBreak, ResultRow

_MULTIPLIERS = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
    "k": 1e3, "K": 1e3, "M": 1e6, "meg": 1e6, "g": 1e9, "G": 1e9,
}

_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _extract_number(text: str) -> float | None:
    """Pulls a leading number (with an optional SI-prefix multiplier right after it) out of text."""
    if not text:
        return None
    text = text.strip()
    m = _NUM_RE.match(text.replace(",", ""))
    if not m:
        return None
    value = float(m.group())
    rest = text[m.end():].strip()
    if rest:
        prefix = rest[0]
        if prefix in _MULTIPLIERS and (len(rest) == 1 or not rest[1].isalpha() or rest[:3].lower() != "meg"):
            value *= _MULTIPLIERS[prefix]
        elif rest[:3].lower() == "meg":
            value *= _MULTIPLIERS["meg"]
    return value


def _values_match(target: ExtractedAttribute, candidate_text: str) -> bool:
    candidate_text = (candidate_text or "").strip()
    target_value = f"{target.value}{target.unit or ''}".strip()

    target_num = _extract_number(target_value)
    candidate_num = _extract_number(candidate_text)
    if target_num is not None and candidate_num is not None:
        if target_num == 0:
            return candidate_num == 0
        return abs(target_num - candidate_num) / abs(target_num) < 0.02

    needles = [target.value.lower()] + [a.lower() for a in target.aliases]
    haystack = candidate_text.lower()
    return any(n in haystack for n in needles if n)


def score_product(attributes: list[ExtractedAttribute], parameters: list[dict]) -> tuple[int, str]:
    if not attributes:
        return 0, "No parametric criteria extracted from the query"

    total = len(attributes)
    matched = 0
    mismatch_notes = []

    for attr in attributes:
        candidate = next(
            (p for p in parameters if attr.name.lower() in (p.get("ParameterText") or "").lower()
             or (p.get("ParameterText") or "").lower() in attr.name.lower()),
            None,
        )
        if candidate and _values_match(attr, candidate.get("ValueText", "")):
            matched += 1
        else:
            found = candidate.get("ValueText") if candidate else "not specified"
            mismatch_notes.append(f"{attr.name}: wanted {attr.value}{attr.unit or ''}, found {found}")

    note = "Exact match on all criteria" if matched == total else "; ".join(mismatch_notes[:2])
    return matched, note


def _stock_status(qty: int) -> str:
    if qty <= 0:
        return "out"
    if qty < 100:
        return "low"
    return "in"


def _is_rohs(classifications: dict) -> bool:
    status = (classifications or {}).get("RohsStatus", "").lower()
    return "compliant" in status and "non-compliant" not in status


def _unit_price(variation: dict, product: dict) -> float:
    pricing = variation.get("StandardPricing") or []
    if pricing:
        return float(pricing[0].get("UnitPrice", 0.0))
    return float(product.get("UnitPrice") or 0.0)


def _price_breaks(variation: dict) -> list[PriceBreak]:
    return [
        PriceBreak(qty=pb.get("BreakQuantity", 0), price=float(pb.get("UnitPrice", 0.0)))
        for pb in (variation.get("StandardPricing") or [])
    ]


def _price_at_qty(breaks: list[PriceBreak], qty: int) -> float | None:
    """Real qty-break price lookup — the unit price of the highest break tier at or
    below `qty` (standard distributor pricing: you pay the tier your order quantity
    qualifies for), falling back to the lowest tier if `qty` is below all of them."""
    if not breaks:
        return None
    applicable = [b for b in breaks if b.qty <= qty]
    if applicable:
        return max(applicable, key=lambda b: b.qty).price
    return min(breaks, key=lambda b: b.qty).price


def _attrs_summary(product: dict, variation: dict) -> str:
    parts = [f"{p.get('ParameterText')}: {p.get('ValueText')}" for p in (product.get("Parameters") or [])[:4]]
    package_type = (variation.get("PackageType") or {}).get("Name")
    if package_type:
        parts.append(package_type)
    return " · ".join(parts)


def flatten_products(products: list[dict], attributes: list[ExtractedAttribute]) -> list[ResultRow]:
    rows: list[ResultRow] = []

    for product in products:
        variations = product.get("ProductVariations") or []
        if not variations:
            continue

        match_score, match_note = score_product(attributes, product.get("Parameters") or [])
        mfr = (product.get("Manufacturer") or {}).get("Name", "")
        mpn = product.get("ManufacturerProductNumber", "")
        lifecycle = (product.get("ProductStatus") or {}).get("Status", "Active")
        classifications = product.get("Classifications") or {}
        rohs = _is_rohs(classifications)
        series = (product.get("Series") or {}).get("Name")
        description = (product.get("Description") or {}).get("ProductDescription") or None
        category = (product.get("Category") or {}).get("Name")
        other_names = product.get("OtherNames") or []

        for variation in variations:
            stock = variation.get("QuantityAvailableforPackageType", product.get("QuantityAvailable", 0))
            price_breaks = _price_breaks(variation)
            alts = [
                Alternate(
                    mpn=f"{mpn} ({(v.get('PackageType') or {}).get('Name', 'alt packaging')})",
                    why=f"MOQ {v.get('MinimumOrderQuantity', 1)}",
                )
                for v in variations
                if v is not variation
            ]

            rows.append(ResultRow(
                dk=variation.get("DigiKeyProductNumber", ""),
                mfr=mfr,
                mpn=mpn,
                attrs=_attrs_summary(product, variation),
                stock=stock,
                status=_stock_status(stock),
                price=_unit_price(variation, product),
                moq=variation.get("MinimumOrderQuantity", 1),
                best=False,
                rohs=rohs,
                lifecycle=lifecycle,
                matchScore=match_score,
                matchTotal=len(attributes),
                matchNote=match_note,
                alts=alts,
                photoUrl=product.get("PhotoUrl") or None,
                datasheetUrl=product.get("DatasheetUrl") or None,
                productUrl=product.get("ProductUrl") or None,
                series=series,
                leadWeeks=product.get("ManufacturerLeadWeeks") or None,
                discontinued=bool(product.get("Discontinued")),
                endOfLife=bool(product.get("EndOfLife")),
                ncnr=bool(product.get("Ncnr")),
                backOrderNotAllowed=bool(product.get("BackOrderNotAllowed")),
                reachStatus=classifications.get("ReachStatus") or None,
                moistureSensitivityLevel=classifications.get("MoistureSensitivityLevel") or None,
                exportControlClassNumber=classifications.get("ExportControlClassNumber") or None,
                htsusCode=classifications.get("HtsusCode") or None,
                manufacturerPublicQuantity=product.get("ManufacturerPublicQuantity"),
                description=description,
                category=category,
                otherNames=other_names,
                marketplace=bool(variation.get("MarketPlace")),
                tariffActive=bool(variation.get("TariffActive")),
                priceBreaks=price_breaks,
                priceAt100=_price_at_qty(price_breaks, 100),
            ))

    # price == 0.0 means no real pricing data was found (see _unit_price), not an
    # actual free part. Rank "has real pricing" ahead of stock/price — a listing
    # with no purchasable price shouldn't out-rank a real one just because its
    # (also often unreliable) stock figure happens to be larger.
    rows.sort(key=lambda r: (-r.matchScore, r.price <= 0, -r.stock, r.price if r.price > 0 else float("inf")))
    if rows:
        rows[0].best = True
    return rows
