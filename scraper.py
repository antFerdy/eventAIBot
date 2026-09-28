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


_EVENT_LINK_RE = re.compile(r"/almaty/event/[a-z0-9-]+")
_PLACE_LINK_RE = re.compile(r"/almaty/place/[a-z0-9-]+")


def discover_event_urls(fetch_fn) -> list[str]:
    """Paginate the afisha listing and return every unique event detail URL."""
    slugs = set()
    for page in range(1, EVENT_LISTING_PAGES + 1):
        html = fetch_fn(f"{BASE_URL}/almaty/afisha?page={page}")
        slugs.update(_EVENT_LINK_RE.findall(html))
    return sorted(f"{BASE_URL}{slug}" for slug in slugs)


def make_fetcher(session: requests.Session, delay: float = REQUEST_DELAY_SECONDS):
    """Return a fetch_fn that GETs a URL through `session`, then politely sleeps."""

    def fetch(url: str) -> str:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        time.sleep(delay)
        return response.text

    return fetch


def discover_place_urls(fetch_fn) -> list[str]:
    """Paginate every place category listing and return every unique place detail URL."""
    slugs = set()
    for category in PLACE_CATEGORIES:
        for page in range(1, PLACE_CATEGORY_PAGES + 1):
            html = fetch_fn(f"{BASE_URL}/almaty/places/{category}?page={page}")
            slugs.update(_PLACE_LINK_RE.findall(html))
    return sorted(f"{BASE_URL}{slug}" for slug in slugs)


def scrape_all(fetch_fn) -> list[dict]:
    """Discover and parse every event and place, skipping any URL that fails."""
    records = []
    for url in discover_event_urls(fetch_fn):
        try:
            html = fetch_fn(url)
        except Exception as exc:
            print(f"skip {url}: {exc}")
            continue
        record = parse_event(html, url)
        if record:
            records.append(record)
    for url in discover_place_urls(fetch_fn):
        try:
            html = fetch_fn(url)
        except Exception as exc:
            print(f"skip {url}: {exc}")
            continue
        record = parse_place(html, url)
        if record:
            records.append(record)
    return records


def save_raw(records: list[dict], path: str = "sxodim_raw.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _session = requests.Session()
    _fetch = make_fetcher(_session)
    _records = scrape_all(_fetch)
    save_raw(_records)
    print(f"Scraped {len(_records)} records -> sxodim_raw.json")
