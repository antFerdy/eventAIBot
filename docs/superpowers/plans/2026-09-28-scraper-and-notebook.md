# Scraper + Notebook Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scraper.py` (a standalone, importable, tested scraping module) and `sxodim_agent.ipynb` (notebook that runs it end-to-end against the live site and shows a data fragment), producing `sxodim_raw.json`.

**Architecture:** `scraper.py` exposes small pure functions for JSON-LD/breadcrumb extraction and record normalization (unit-tested against saved HTML fixtures, no network in tests), plus discovery/orchestration functions that take an injected `fetch_fn` so they're testable without hitting the network. The notebook imports these functions, supplies a real `requests`-backed fetcher, runs the full scrape once, and displays/saves the result. This is the scraping stage only (stage 1 of the 4-stage pipeline in the spec); tagging/agent/ORPO are separate future plans.

**Tech Stack:** Python 3.12 (project venv at `.venv/`, not the system Python 3.14 — see Global Constraints), `requests` for HTTP, `pytest` for tests, `jupyter`+`ipykernel` for the notebook. No BeautifulSoup, no Crawl4AI/Firecrawl, no LangChain.

**Spec:** `docs/superpowers/specs/2026-09-28-sxodim-agent-design.md`

## Global Constraints

- Fully local, no paid APIs (spec §2).
- Minimum magic: explicit, narrow functions; no scraping frameworks (spec §2, §3).
- Scraping happens once, offline, into a file; the agent (future work) never scrapes live at question time (spec §2).
- Event discovery: paginate `https://sxodim.com/almaty/afisha?page=1..9` only — verified live, page 10 is empty, `date_from`/`date_to` params have no effect (spec §4.1).
- Place discovery: first 2 pages of each of the 22 category listings under `/almaty/places/<category>?page=1,2`, not the general 119-page listing (spec §4.1). Category slugs: `anticafe, aquapark, bars, beauty-health, biblioteki-, cafe, cinema, coffee-house, countryside, coworkings, dlja-detej, education, entertainment, hotels, karaoke, konditerskaya, museums, parks, prokat-snaryazheniya, recreation, restaurants, theatres`.
- Polite delay of ~0.3s between requests (spec §4.1).
- Output file: `sxodim_raw.json` (spec §5). This is the raw stage; the normalized+tagged `sxodim_data.json` required by the ТЗ is produced by a later plan (spec §4.2).
- Use Python 3.12 (`/opt/homebrew/bin/python3.12`) for the project venv, not system Python 3.14 — chosen now (not deferred to the ORPO phase as the spec's §4.4 literally scopes it) so there's a single venv for the whole project instead of two; 3.12 has full wheel support for everything the spec needs, including the later `torch`/`trl` stack.

## Review Focus

- A single bad/unreachable detail page (HTTP error) must not abort the entire ~800-request scrape — it should be skipped and logged, not crash the run. → Task 7.
- A malformed JSON-LD block (invalid JSON) on a page must not crash extraction — it should be skipped, other blocks on the same page still parsed. → Task 3.
- A free event (no `offers` in its `Event` JSON-LD) must yield `price: None`, not a `KeyError`/crash. → Task 4.
- A place with zero reviews (no `aggregateRating` block) must yield `rating: None`, not a crash. → Task 4.
- A place appearing in two different category listings (e.g. both `cafe` and `restaurants`) must be discovered once, not scraped/recorded twice. → Task 5.

---

## Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create (dirs): `tests/fixtures/`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a `.venv/` virtualenv on the project root with `requests`, `pytest`, `jupyter`, `ipykernel` installed, and a registered Jupyter kernel named `python3`, which every later task's commands assume is activated.

- [ ] **Step 1: Create the venv with Python 3.12**

Run: `/opt/homebrew/bin/python3.12 -m venv /Users/rustem/Documents/N_Factorial/SxodimBot/.venv`
Expected: no output, `.venv/bin/python` now exists.

- [ ] **Step 2: Write `requirements.txt`**

```
requests
pytest
jupyter
ipykernel
```

- [ ] **Step 3: Install requirements into the venv**

Run: `source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt`
Expected: exits 0, ends with "Successfully installed ...".

- [ ] **Step 4: Register the venv as a Jupyter kernel**

Run: `source .venv/bin/activate && python -m ipykernel install --user --name python3 --display-name "Python (sxodim)"`
Expected: prints "Installed kernelspec python3 in ...".

- [ ] **Step 5: Verify the install**

Run: `source .venv/bin/activate && python -c "import requests, pytest, jupyter; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.ipynb_checkpoints/
.pytest_cache/
```

- [ ] **Step 7: Create the fixtures directory**

Run: `mkdir -p tests/fixtures`

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "chore: add project venv setup (requirements, gitignore)"
```

---

## Task 2: HTML fixtures for tests

**Files:**
- Create: `tests/fixtures/event_page.html`
- Create: `tests/fixtures/place_page.html`

**Interfaces:**
- Consumes: nothing.
- Produces: two real, saved HTML pages (one event detail page, one place detail page) that Tasks 3-4's tests load and assert against by exact known content.

- [ ] **Step 1: Copy the already-fetched real pages into the fixtures directory**

Run:
```bash
cp /tmp/sxodim_event.html tests/fixtures/event_page.html
cp /tmp/sxodim_place.html tests/fixtures/place_page.html
```
Expected: both files exist and are non-empty.

- [ ] **Step 2: Verify fixture contents**

Run: `grep -c 'application/ld+json' tests/fixtures/event_page.html tests/fixtures/place_page.html`
Expected: both files report 3 (three JSON-LD blocks each: Article, Event/LocalBusiness, BreadcrumbList).

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/event_page.html tests/fixtures/place_page.html
git commit -m "test: add real event/place page HTML fixtures"
```

---

## Task 3: JSON-LD and breadcrumb extraction

**Files:**
- Create: `scraper.py`
- Create: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `tests/fixtures/event_page.html`, `tests/fixtures/place_page.html` (Task 2).
- Produces:
  - `scraper.BASE_URL: str`
  - `scraper.PLACE_CATEGORIES: list[str]`
  - `scraper.EVENT_LISTING_PAGES: int`
  - `scraper.PLACE_CATEGORY_PAGES: int`
  - `scraper.REQUEST_DELAY_SECONDS: float`
  - `scraper.extract_json_ld_blocks(html: str) -> list[dict]`
  - `scraper.extract_breadcrumb_category(html: str) -> str | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scraper.py`:

```python
from pathlib import Path

import scraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_extract_json_ld_blocks_finds_event_block():
    html = load_fixture("event_page.html")
    blocks = scraper.extract_json_ld_blocks(html)
    types = [b.get("@type") for b in blocks]
    assert "Event" in types


def test_extract_json_ld_blocks_skips_malformed_json():
    html = (
        '<script type="application/ld+json">{not valid json}</script>'
        '<script type="application/ld+json">{"@type": "Event", "name": "ok"}</script>'
    )
    blocks = scraper.extract_json_ld_blocks(html)
    assert blocks == [{"@type": "Event", "name": "ok"}]


def test_extract_breadcrumb_category_for_event():
    html = load_fixture("event_page.html")
    assert scraper.extract_breadcrumb_category(html) == "Концерты"


def test_extract_breadcrumb_category_for_place():
    html = load_fixture("place_page.html")
    assert scraper.extract_breadcrumb_category(html) == "Кофейни"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper'`.

- [ ] **Step 3: Write the implementation**

Create `scraper.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: extract JSON-LD blocks and breadcrumb category from sxodim pages"
```

---

## Task 4: Normalize events and places into records

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `scraper.extract_json_ld_blocks`, `scraper.extract_breadcrumb_category` (Task 3).
- Produces:
  - `scraper.parse_event(html: str, url: str) -> dict | None`
  - `scraper.parse_place(html: str, url: str) -> dict | None`
  - Both return a dict with exactly these keys on success: `type, url, name, category, description, address, date_start, price, currency, rating, image`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scraper.py`:

```python
def test_parse_event_extracts_known_fields():
    html = load_fixture("event_page.html")
    record = scraper.parse_event(
        html, "https://sxodim.com/almaty/event/abzal-uteshovty-koncerti"
    )
    assert record["type"] == "event"
    assert record["name"] == "Абзал Утешов Алматыда (7 қазан, 16:00)"
    assert record["category"] == "Концерты"
    assert record["price"] == 12000
    assert record["currency"] == "KZT"
    assert record["date_start"] == "2026-10-07T16:00:00+05:00"
    assert record["address"] == "Республика сарайы, Достық даңғылы, 56"


def test_parse_event_returns_none_for_non_event_page():
    html = load_fixture("place_page.html")
    assert scraper.parse_event(html, "https://sxodim.com/almaty/place/x") is None


def test_parse_event_handles_missing_offers():
    html = (
        '<script type="application/ld+json">'
        '{"@context": "http://schema.org", "@type": "Event", "name": "Free Concert",'
        ' "description": "desc", "startDate": "2026-01-01T00:00:00+05:00",'
        ' "location": {"@type": "Place", "address":'
        ' {"@type": "PostalAddress", "streetAddress": "Somewhere"}}}'
        "</script>"
    )
    record = scraper.parse_event(html, "https://sxodim.com/almaty/event/free-concert")
    assert record["price"] is None
    assert record["currency"] is None
    assert record["address"] == "Somewhere"


def test_parse_place_extracts_known_fields():
    html = load_fixture("place_page.html")
    record = scraper.parse_place(
        html, "https://sxodim.com/almaty/place/kofeynya-gastronom"
    )
    assert record["type"] == "place"
    assert record["name"] == "Кофейня «Гастроном»"
    assert record["category"] == "Кофейни"
    assert record["rating"] == 5
    assert record["address"] == "Алматы, проспект Жибек Жолы, 53"
    assert record["description"].startswith("Здесь все по-простому")


def test_parse_place_returns_none_for_non_place_page():
    html = load_fixture("event_page.html")
    assert scraper.parse_place(html, "https://sxodim.com/almaty/event/x") is None


def test_parse_place_handles_missing_rating():
    html = (
        '<script type="application/ld+json">'
        '{"@context": "http://schema.org", "@type": "LocalBusiness", "name": "New Place",'
        ' "address": {"@type": "PostalAddress", "streetAddress": "Somewhere"}}'
        "</script>"
        '<script type="application/ld+json">'
        '{"@context": "http://schema.org", "@type": "Article", "description": "A new cafe."}'
        "</script>"
    )
    record = scraper.parse_place(html, "https://sxodim.com/almaty/place/new-place")
    assert record["rating"] is None
    assert record["description"] == "A new cafe."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: FAIL with `AttributeError: module 'scraper' has no attribute 'parse_event'`.

- [ ] **Step 3: Write the implementation**

Append to `scraper.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: normalize event and place JSON-LD into record dicts"
```

---

## Task 5: URL discovery (events + places)

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `scraper.BASE_URL`, `scraper.EVENT_LISTING_PAGES`, `scraper.PLACE_CATEGORIES`, `scraper.PLACE_CATEGORY_PAGES` (Task 3).
- Produces:
  - `scraper.discover_event_urls(fetch_fn: Callable[[str], str]) -> list[str]`
  - `scraper.discover_place_urls(fetch_fn: Callable[[str], str]) -> list[str]`
  - Both return a sorted, deduped list of full `https://sxodim.com/almaty/...` URLs. `fetch_fn` takes a URL string and returns the page's HTML as a string — Task 7 supplies the real network-backed one from Task 6.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scraper.py`:

```python
def test_discover_event_urls_paginates_and_dedupes():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        page = int(url.rsplit("page=", 1)[1])
        return f'<a href="/almaty/event/item-{page}">x</a><a href="/almaty/event/item-1">dup</a>'

    urls = scraper.discover_event_urls(fake_fetch)
    assert len(calls) == scraper.EVENT_LISTING_PAGES
    assert urls == sorted(
        f"{scraper.BASE_URL}/almaty/event/item-{p}"
        for p in range(1, scraper.EVENT_LISTING_PAGES + 1)
    )


def test_discover_place_urls_covers_every_category_and_page():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return '<a href="/almaty/place/sample-place">x</a>'

    urls = scraper.discover_place_urls(fake_fetch)
    assert len(calls) == len(scraper.PLACE_CATEGORIES) * scraper.PLACE_CATEGORY_PAGES
    assert urls == [f"{scraper.BASE_URL}/almaty/place/sample-place"]


def test_discover_place_urls_dedupes_across_categories(monkeypatch):
    monkeypatch.setattr(scraper, "PLACE_CATEGORIES", ["cafe", "restaurants"])
    monkeypatch.setattr(scraper, "PLACE_CATEGORY_PAGES", 1)

    def fake_fetch(url):
        return '<a href="/almaty/place/shared-place">x</a>'

    urls = scraper.discover_place_urls(fake_fetch)
    assert urls == [f"{scraper.BASE_URL}/almaty/place/shared-place"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: FAIL with `AttributeError: module 'scraper' has no attribute 'discover_event_urls'`.

- [ ] **Step 3: Write the implementation**

Append to `scraper.py`:

```python
_EVENT_LINK_RE = re.compile(r"/almaty/event/[a-z0-9-]+")
_PLACE_LINK_RE = re.compile(r"/almaty/place/[a-z0-9-]+")


def discover_event_urls(fetch_fn) -> list[str]:
    """Paginate the afisha listing and return every unique event detail URL."""
    slugs = set()
    for page in range(1, EVENT_LISTING_PAGES + 1):
        html = fetch_fn(f"{BASE_URL}/almaty/afisha?page={page}")
        slugs.update(_EVENT_LINK_RE.findall(html))
    return sorted(f"{BASE_URL}{slug}" for slug in slugs)


def discover_place_urls(fetch_fn) -> list[str]:
    """Paginate every place category listing and return every unique place detail URL."""
    slugs = set()
    for category in PLACE_CATEGORIES:
        for page in range(1, PLACE_CATEGORY_PAGES + 1):
            html = fetch_fn(f"{BASE_URL}/almaty/places/{category}?page={page}")
            slugs.update(_PLACE_LINK_RE.findall(html))
    return sorted(f"{BASE_URL}{slug}" for slug in slugs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: PASS (14 passed).

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: discover event and place detail URLs via listing pagination"
```

---

## Task 6: Real HTTP fetcher

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `scraper.REQUEST_DELAY_SECONDS` (Task 3).
- Produces: `scraper.make_fetcher(session: requests.Session, delay: float = REQUEST_DELAY_SECONDS) -> Callable[[str], str]` — the real `fetch_fn` implementation Task 7's orchestration and the notebook will pass to `discover_event_urls`/`discover_place_urls`/`scrape_all`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scraper.py`:

```python
def test_make_fetcher_gets_url_and_sleeps(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr(scraper.time, "sleep", lambda s: sleep_calls.append(s))

    class FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self):
            pass

    class FakeSession:
        def __init__(self):
            self.requested = []

        def get(self, url, timeout):
            self.requested.append((url, timeout))
            return FakeResponse()

    session = FakeSession()
    fetch = scraper.make_fetcher(session, delay=0.5)
    result = fetch("https://sxodim.com/almaty")

    assert result == "<html>ok</html>"
    assert session.requested == [("https://sxodim.com/almaty", 10)]
    assert sleep_calls == [0.5]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: FAIL with `AttributeError: module 'scraper' has no attribute 'make_fetcher'`.

- [ ] **Step 3: Write the implementation**

Append to `scraper.py`:

```python
def make_fetcher(session: requests.Session, delay: float = REQUEST_DELAY_SECONDS):
    """Return a fetch_fn that GETs a URL through `session`, then politely sleeps."""

    def fetch(url: str) -> str:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        time.sleep(delay)
        return response.text

    return fetch
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: PASS (15 passed).

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: add requests-backed fetcher with rate limiting"
```

---

## Task 7: Orchestration and output

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `scraper.discover_event_urls`, `scraper.discover_place_urls`, `scraper.parse_event`, `scraper.parse_place`, `scraper.make_fetcher` (Tasks 4-6).
- Produces:
  - `scraper.scrape_all(fetch_fn) -> list[dict]`
  - `scraper.save_raw(records: list[dict], path: str = "sxodim_raw.json") -> None`
  - A `python scraper.py` CLI entry point that runs a real scrape and writes `sxodim_raw.json` — the standalone "script for scraping the site" the notebook will also be able to call into.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scraper.py` (add `import json` to the top of the file):

```python
def test_scrape_all_combines_events_and_places(monkeypatch, tmp_path):
    monkeypatch.setattr(scraper, "PLACE_CATEGORIES", ["cafe"])
    monkeypatch.setattr(scraper, "EVENT_LISTING_PAGES", 1)
    monkeypatch.setattr(scraper, "PLACE_CATEGORY_PAGES", 1)

    event_html = load_fixture("event_page.html")
    place_html = load_fixture("place_page.html")

    def fake_fetch(url):
        if "afisha" in url:
            return '<a href="/almaty/event/abzal-uteshovty-koncerti">x</a>'
        if "/places/cafe" in url:
            return '<a href="/almaty/place/kofeynya-gastronom">x</a>'
        if "/event/" in url:
            return event_html
        if "/place/" in url:
            return place_html
        raise AssertionError(f"unexpected url {url}")

    records = scraper.scrape_all(fake_fetch)
    assert {r["type"] for r in records} == {"event", "place"}
    assert len(records) == 2

    output_path = tmp_path / "sxodim_raw.json"
    scraper.save_raw(records, str(output_path))
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == records


def test_scrape_all_skips_urls_that_fail_to_fetch(monkeypatch):
    monkeypatch.setattr(scraper, "PLACE_CATEGORIES", ["cafe"])
    monkeypatch.setattr(scraper, "EVENT_LISTING_PAGES", 1)
    monkeypatch.setattr(scraper, "PLACE_CATEGORY_PAGES", 1)

    place_html = load_fixture("place_page.html")

    def fake_fetch(url):
        if "afisha" in url:
            return '<a href="/almaty/event/broken-event">x</a>'
        if "/places/cafe" in url:
            return '<a href="/almaty/place/kofeynya-gastronom">x</a>'
        if "/event/broken-event" in url:
            raise scraper.requests.exceptions.HTTPError("404")
        if "/place/" in url:
            return place_html
        raise AssertionError(f"unexpected url {url}")

    records = scraper.scrape_all(fake_fetch)
    assert len(records) == 1
    assert records[0]["type"] == "place"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: FAIL with `AttributeError: module 'scraper' has no attribute 'scrape_all'`.

- [ ] **Step 3: Write the implementation**

Append to `scraper.py`:

```python
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
```

Add `import json` to the top imports of `scraper.py` (it should already be there from Task 3).

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_scraper.py -v`
Expected: PASS (17 passed).

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: orchestrate full scrape with error handling, add CLI entry point"
```

---

## Task 8: Notebook

**Files:**
- Create: `sxodim_agent.ipynb`

**Interfaces:**
- Consumes: `scraper.make_fetcher`, `scraper.scrape_all`, `scraper.save_raw` (Task 7).
- Produces: `sxodim_raw.json` in the project root (committed as evidence), and an executed notebook with visible outputs satisfying the ТЗ's "Вывод парсера (фрагмент данных)" requirement for this stage.

- [ ] **Step 1: Write the notebook**

Create `sxodim_agent.ipynb` with this exact nbformat v4 content:

```json
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# Агент \"Куда сходить в Алматы\"\n",
    "\n",
    "ТЗ #2: парсинг sxodim.com/almaty + агент, отвечающий на вопросы о том, куда сходить.\n",
    "\n",
    "## Раздел 1: Парсинг сайта\n",
    "\n",
    "Скрейпинг запускается один раз и кэшируется в `sxodim_raw.json` — при повторном запуске ноутбука сеть не дёргается, если файл уже существует. Логика парсинга живёт в `scraper.py` (см. рядом), ноутбук только вызывает её и показывает результат."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "import json\n",
    "from pathlib import Path\n",
    "\n",
    "import requests\n",
    "\n",
    "import scraper\n",
    "\n",
    "RAW_PATH = Path(\"sxodim_raw.json\")"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "if RAW_PATH.exists():\n",
    "    records = json.loads(RAW_PATH.read_text(encoding=\"utf-8\"))\n",
    "    print(f\"Loaded {len(records)} cached records from {RAW_PATH}\")\n",
    "else:\n",
    "    session = requests.Session()\n",
    "    fetch = scraper.make_fetcher(session)\n",
    "    records = scraper.scrape_all(fetch)\n",
    "    scraper.save_raw(records, str(RAW_PATH))\n",
    "    print(f\"Scraped {len(records)} records -> {RAW_PATH}\")"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "events = [r for r in records if r[\"type\"] == \"event\"]\n",
    "places = [r for r in records if r[\"type\"] == \"place\"]\n",
    "print(f\"events: {len(events)}, places: {len(places)}, total: {len(records)}\")"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "print(\"Пример события:\")\n",
    "print(json.dumps(events[0], ensure_ascii=False, indent=2))\n",
    "print()\n",
    "print(\"Пример места:\")\n",
    "print(json.dumps(places[0], ensure_ascii=False, indent=2))"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "Дальше (следующий этап, отдельным пайплайном): нормализация в `sxodim_data.json` с семантическими тегами и сам агент — см. `docs/superpowers/specs/2026-09-28-sxodim-agent-design.md`."
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python (sxodim)",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "name": "python",
   "version": "3.12"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
```

- [ ] **Step 2: Execute the notebook for real, in the background**

This performs the actual live scrape (~800 requests, several minutes) — run it in the background rather than blocking:

Run (background): `source .venv/bin/activate && jupyter nbconvert --to notebook --execute --inplace sxodim_agent.ipynb --ExecutePreprocessor.kernel_name=python3 --ExecutePreprocessor.timeout=1800`
Expected (once finished): exits 0, `sxodim_agent.ipynb` is rewritten in place with populated `outputs` on every code cell, and `sxodim_raw.json` now exists in the project root.

- [ ] **Step 3: Verify the notebook outputs and the data file**

Run: `source .venv/bin/activate && jupyter nbconvert --to script --stdout sxodim_agent.ipynb | head -5 && python -c "import json; d = json.load(open('sxodim_raw.json')); print(len(d), 'records'); print({r['type'] for r in d})"`
Expected: prints the record count (order of a few hundred) and `{'event', 'place'}`.

- [ ] **Step 4: Commit**

```bash
git add sxodim_agent.ipynb sxodim_raw.json
git commit -m "feat: add notebook running the scraper end-to-end with outputs"
```
