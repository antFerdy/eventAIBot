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
