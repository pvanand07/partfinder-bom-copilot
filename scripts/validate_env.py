"""Phase 0 smoke test — hits the real DigiKey and OpenRouter APIs using the
credentials in .env, before any of the rest of the backend is trusted to work.

Run: python scripts/validate_env.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from server.digikey_client import DigikeyClient, DigikeyError
from server.nl_parser import parse_query


def check_digikey() -> bool:
    print("--- DigiKey (production, client-credentials) ---")
    try:
        client = DigikeyClient()
        result = client.keyword_search("10k 0603 resistor", record_count=3)
    except DigikeyError as exc:
        print(f"FAIL: {exc}")
        return False

    count = result.get("ProductsCount")
    products = result.get("Products", [])
    print(f"OK: ProductsCount={count}, returned {len(products)} products")
    if products:
        p = products[0]
        print(f"    sample: {p.get('ManufacturerProductNumber')} by {(p.get('Manufacturer') or {}).get('Name')}")
    return True


def check_openrouter() -> bool:
    print("--- OpenRouter (structured extraction) ---")
    try:
        result = parse_query("10k 0603 1% resistor for a voltage divider, tape and reel")
    except Exception as exc:
        print(f"FAIL: {exc}")
        return False

    print(f"OK: {len(result.items)} item(s) extracted, rationale={result.rationale!r}")
    for item in result.items:
        print(f"    keywords={item.keywords!r} attributes={[(a.name, a.value, a.unit) for a in item.attributes]}")
    return True


if __name__ == "__main__":
    ok_digikey = check_digikey()
    ok_openrouter = check_openrouter()

    print()
    if ok_digikey and ok_openrouter:
        print("Phase 0 PASSED — both dependencies confirmed live.")
        sys.exit(0)
    else:
        print("Phase 0 FAILED — fix the above before continuing.")
        sys.exit(1)
