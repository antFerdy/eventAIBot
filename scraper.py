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


def parse_event(html: str, url: str) -> dict | None:
    event_block = next(
        (b for b in extract_json_ld_blocks(html) if b.get("@type") == "Event"), None
    )
    if event_block is None:
        return None
    offers = event_block.get("offers") or {}
    location = event_block.get("location") or {}
    address = (location.get("address") or {}).get("streetAddress")
    image = event_block.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    return {
        "type": "event",
        "url": url,
        "name": event_block.get("name"),
        "category": extract_breadcrumb_category(html),
        "description": event_block.get("description"),
        "address": address,
        "date_start": event_block.get("startDate"),
        "price": offers.get("price"),
        "currency": offers.get("priceCurrency"),
        "rating": None,
        "image": image,
    }


def parse_place(html: str, url: str) -> dict | None:
    blocks = extract_json_ld_blocks(html)
    place_block = next((b for b in blocks if b.get("@type") == "LocalBusiness"), None)
    if place_block is None:
        return None
    article_block = next((b for b in blocks if b.get("@type") == "Article"), None)
    address = (place_block.get("address") or {}).get("streetAddress")
    rating = (place_block.get("aggregateRating") or {}).get("ratingValue")
    return {
        "type": "place",
        "url": url,
        "name": place_block.get("name"),
        "category": extract_breadcrumb_category(html),
        "description": (article_block or {}).get("description"),
        "address": address,
        "date_start": None,
        "price": None,
        "currency": None,
        "rating": rating,
        "image": place_block.get("image"),
    }
