import json
import re
import time

import requests

BASE_URL = "https://sxodim.com"

PLACE_CATEGORIES = [
    "anticafe", "aquapark", "bars", "beauty-health", "biblioteki-", "cafe",
    "cinema", "coffee-house", "countryside", "coworkings", "dlja-detej",
    "education", "entertainment", "hotels", "karaoke", "konditerskaya",
    "museums", "parks", "prokat-snaryazheniya", "recreation", "restaurants",
    "theatres",
]

EVENT_LISTING_PAGES = 9
PLACE_CATEGORY_PAGES = 2
REQUEST_DELAY_SECONDS = 0.3

_JSON_LD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S
)


def extract_json_ld_blocks(html: str) -> list[dict]:
    """Return every parseable JSON-LD block found in an HTML page."""
    blocks = []
    for raw in _JSON_LD_RE.findall(html):
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blocks


def extract_breadcrumb_category(html: str) -> str | None:
    """Return the breadcrumb entry just above the page itself, e.g. 'Концерты'."""
    for block in extract_json_ld_blocks(html):
        if block.get("@type") == "BreadcrumbList":
            items = block.get("itemListElement", [])
            if len(items) >= 2:
                return items[-2].get("name")
    return None
