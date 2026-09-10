import os
import re
from datetime import datetime, timedelta

import requests

PROD_HOST = "api.digikey.com"
SANDBOX_HOST = "sandbox-api.digikey.com"

# DigiKey's keyword search silently returns zero results (no error) if the
# query contains certain non-ASCII symbols — confirmed live: "10kΩ resistor"
# -> 0 products, "10k ohm resistor" -> 2611 products, otherwise identical.
# Sanitize defensively regardless of what the caller (LLM output) sends.
_SYMBOL_REPLACEMENTS = {
    "Ω": "ohm",  # GREEK CAPITAL LETTER OMEGA (what LLMs typically emit for "ohm")
    "Ω": "ohm",  # OHM SIGN (visually identical, distinct codepoint)
    "µ": "u",    # MICRO SIGN
    "μ": "u",    # GREEK SMALL LETTER MU
    "±": "",     # PLUS-MINUS SIGN
    "°": " deg", # DEGREE SIGN
}


def _sanitize_keywords(keywords: str) -> str:
    keywords = re.sub(r"(\d+)\s*percent", r"\1%", keywords, flags=re.IGNORECASE)
    for symbol, replacement in _SYMBOL_REPLACEMENTS.items():
        keywords = keywords.replace(symbol, replacement)
    keywords = keywords.encode("ascii", "ignore").decode("ascii")
    return " ".join(keywords.split())


class DigikeyError(Exception):
    pass


class DigikeyClient:
    """Client-credentials (2-legged OAuth2) DigiKey Product Search v4 client.

    Confirmed live against production (api.digikey.com) during planning —
    see the plan's "Blocker — RESOLVED on production" section. Defaults to
    production; set DIGIKEY_CLIENT_SANDBOX=true to use the sandbox host.
    """

    def __init__(self):
        self.client_id = os.getenv("DIGIKEY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("DIGIKEY_CLIENT_SECRET", "").strip()
        if not self.client_id or not self.client_secret:
            raise DigikeyError("Missing DIGIKEY_CLIENT_ID or DIGIKEY_CLIENT_SECRET in environment")

        sandbox = os.getenv("DIGIKEY_CLIENT_SANDBOX", "false").strip().lower() in ("1", "true", "yes")
        self.host = SANDBOX_HOST if sandbox else PROD_HOST

        self._access_token = None
        self._token_expiry = None

    def _get_access_token(self) -> str:
        if self._access_token and self._token_expiry and datetime.now() < self._token_expiry:
            return self._access_token

        resp = requests.post(
            f"https://{self.host}/v1/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=15,
        )
        if not resp.ok:
            raise DigikeyError(f"DigiKey token request failed ({resp.status_code}): {resp.text[:500]}")

        token_data = resp.json()
        self._access_token = token_data["access_token"]
        # refresh a little early to avoid edge-of-expiry failures
        self._token_expiry = datetime.now() + timedelta(seconds=token_data["expires_in"] - 30)
        return self._access_token

    def _raw_keyword_search(self, keywords: str, search_options: list[str] | None, record_count: int) -> dict:
        access_token = self._get_access_token()

        body: dict = {"Keywords": keywords, "Limit": record_count, "Offset": 0}
        if search_options:
            body["Filters"] = {"SearchOptions": search_options}

        resp = requests.post(
            f"https://{self.host}/products/v4/search/keyword",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-DIGIKEY-Client-Id": self.client_id,
                "X-DIGIKEY-Locale-Site": "US",
                "X-DIGIKEY-Locale-Language": "en",
                "X-DIGIKEY-Locale-Currency": "USD",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=20,
        )
        if not resp.ok:
            raise DigikeyError(f"DigiKey keyword_search failed ({resp.status_code}): {resp.text[:500]}")

        return resp.json()

    def keyword_search(self, keywords: str, search_options: list[str] | None = None, record_count: int = 25) -> dict:
        """Searches DigiKey by keyword, with a resilience net against overly-specific queries.

        Confirmed live: DigiKey's keyword search behaves like an AND across every word in
        `Keywords`, matched against part numbers/descriptions — not a fuzzy full-text search.
        A query with non-part-description filler (packaging wording, application context) can
        silently return zero results even when the underlying part clearly exists. Since an LLM
        occasionally emits such filler despite prompt instructions not to, we retry with a
        progressively shortened query before giving up — this is what actually makes the "no
        results" state in the UI mean "genuinely no matching parts" rather than "our keyword
        string happened to be too specific."
        """
        keywords = _sanitize_keywords(keywords)
        result = self._raw_keyword_search(keywords, search_options, record_count)

        words = keywords.split()
        for n in (4, 2):
            if result.get("Products"):
                break
            if len(words) <= n:
                continue
            result = self._raw_keyword_search(" ".join(words[:n]), search_options, record_count)

        return result
