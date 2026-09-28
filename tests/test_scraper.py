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
