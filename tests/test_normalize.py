import json

import normalize


def test_slug_from_url_event():
    url = "https://sxodim.com/almaty/event/abzal-uteshovty-koncerti"
    assert normalize.slug_from_url(url, "event") == "event-abzal-uteshovty-koncerti"


def test_slug_from_url_place():
    url = "https://sxodim.com/almaty/place/kofeynya-gastronom"
    assert normalize.slug_from_url(url, "place") == "place-kofeynya-gastronom"


def test_derive_tags_matches_keyword_in_category():
    assert normalize.derive_tags("Концерты во Дворце Республики", None) == ["концерт"]


def test_derive_tags_matches_multiple_distinct_keywords():
    assert normalize.derive_tags("Антикафе", None) == ["активный_отдых", "еда"]


def test_derive_tags_adds_free_tag_when_price_is_zero():
    assert normalize.derive_tags("Концерты", 0) == ["бесплатно", "концерт"]


def test_derive_tags_price_none_no_free_tag():
    assert "бесплатно" not in normalize.derive_tags("Концерты", None)


def test_derive_tags_unmatched_category_returns_empty():
    assert normalize.derive_tags("Отели", None) == []


def test_derive_tags_handles_none_category():
    assert normalize.derive_tags(None, None) == []


def test_normalize_record_adds_id_and_tags_keeps_other_fields():
    raw = {
        "type": "event",
        "url": "https://sxodim.com/almaty/event/abzal-uteshovty-koncerti",
        "name": "Абзал Утешов Алматыда",
        "category": "Концерты",
        "description": "desc",
        "address": "addr",
        "date_start": "2026-10-07T20:00:00+05:00",
        "price": 11000,
        "currency": "KZT",
        "rating": None,
        "image": "https://example.com/img.jpg",
    }
    record = normalize.normalize_record(raw)
    assert record["id"] == "event-abzal-uteshovty-koncerti"
    assert record["tags"] == ["концерт"]
    assert record["name"] == raw["name"]
    assert record["price"] == 11000


def test_normalize_all_dedupes_by_id():
    raw = {
        "type": "place",
        "url": "https://sxodim.com/almaty/place/x",
        "name": "X",
        "category": "Бары",
        "description": None,
        "address": None,
        "date_start": None,
        "price": None,
        "currency": None,
        "rating": None,
        "image": None,
    }
    records = normalize.normalize_all([raw, dict(raw)])
    assert len(records) == 1


def test_save_data_writes_json(tmp_path):
    records = [{"id": "event-x", "type": "event", "name": "X"}]
    path = tmp_path / "sxodim_data.json"
    normalize.save_data(records, str(path))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == records
