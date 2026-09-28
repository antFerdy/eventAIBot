import json
from datetime import datetime, timedelta, timezone

import agent

ALMATY_TZ = timezone(timedelta(hours=5))


def _event(name, date_start, tags=None, price=None, rating=None):
    return {
        "id": f"event-{name}",
        "type": "event",
        "name": name,
        "category": "Концерты",
        "tags": tags or [],
        "description": "desc",
        "address": "addr",
        "date_start": date_start,
        "price": price,
        "currency": "KZT" if price is not None else None,
        "rating": rating,
        "url": f"https://sxodim.com/almaty/event/{name}",
        "image": None,
    }


def _place(name, tags=None, rating=None):
    return {
        "id": f"place-{name}",
        "type": "place",
        "name": name,
        "category": "Рестораны",
        "tags": tags or [],
        "description": "desc",
        "address": "addr",
        "date_start": None,
        "price": None,
        "currency": None,
        "rating": rating,
        "url": f"https://sxodim.com/almaty/place/{name}",
        "image": None,
    }


# Wednesday 2026-09-30, 12:00 Almaty time
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=ALMATY_TZ)


def test_filter_candidates_date_today_matches_only_todays_event():
    data = [
        _event("today-show", "2026-09-30T19:00:00+05:00"),
        _event("tomorrow-show", "2026-10-01T19:00:00+05:00"),
        _place("some-cafe"),
    ]
    result = agent.filter_candidates(
        data, {"date_filter": "today", "intent_tags": [], "price_max": None}, now=NOW
    )
    names = {r["name"] for r in result}
    assert "today-show" in names
    assert "tomorrow-show" not in names
    assert "some-cafe" in names  # places always pass a date filter


def test_filter_candidates_date_weekend_matches_upcoming_saturday_and_sunday():
    data = [
        _event("sat-show", "2026-10-03T19:00:00+05:00"),  # Saturday
        _event("sun-show", "2026-10-04T19:00:00+05:00"),  # Sunday
        _event("mon-show", "2026-10-05T19:00:00+05:00"),  # Monday
    ]
    result = agent.filter_candidates(
        data, {"date_filter": "weekend", "intent_tags": [], "price_max": None}, now=NOW
    )
    names = {r["name"] for r in result}
    assert names == {"sat-show", "sun-show"}


def test_filter_candidates_date_week_matches_within_seven_days():
    data = [
        _event("in-3-days", "2026-10-03T19:00:00+05:00"),
        _event("in-10-days", "2026-10-10T19:00:00+05:00"),
    ]
    result = agent.filter_candidates(
        data, {"date_filter": "week", "intent_tags": [], "price_max": None}, now=NOW
    )
    names = {r["name"] for r in result}
    assert "in-3-days" in names
    assert "in-10-days" not in names


def test_filter_candidates_price_max_excludes_expensive_events_keeps_priceless_places():
    data = [
        _event("cheap-show", "2026-10-03T19:00:00+05:00", price=2000),
        _event("pricey-show", "2026-10-03T19:00:00+05:00", price=20000),
        _place("free-park"),
    ]
    result = agent.filter_candidates(
        data, {"date_filter": "any", "intent_tags": [], "price_max": 5000}, now=NOW
    )
    names = {r["name"] for r in result}
    assert names == {"cheap-show", "free-park"}


def test_filter_candidates_prefers_tag_matches_when_enough_exist():
    data = [_place(f"romantic-{i}", tags=["романтика"]) for i in range(4)] + [
        _place(f"other-{i}") for i in range(4)
    ]
    result = agent.filter_candidates(
        data,
        {"date_filter": "any", "intent_tags": ["романтика"], "price_max": None},
        now=NOW,
    )
    assert all("романтика" in r["tags"] for r in result)


def test_filter_candidates_falls_back_to_full_pool_when_too_few_tag_matches():
    data = [_place("only-romantic", tags=["романтика"])] + [
        _place(f"other-{i}") for i in range(5)
    ]
    result = agent.filter_candidates(
        data,
        {"date_filter": "any", "intent_tags": ["романтика"], "price_max": None},
        now=NOW,
    )
    # fewer than agent.MIN_TAG_MATCHES tag matches -> fall back to the whole pool
    assert len(result) == 6


def test_filter_candidates_ranks_by_rating_not_by_type_when_date_is_not_the_point():
    data = [
        _event("random-workshop", "2026-10-03T19:00:00+05:00", tags=["еда"]),
        _place("top-rated-cafe", tags=["еда"], rating=5),
    ]
    result = agent.filter_candidates(
        data, {"date_filter": "any", "intent_tags": ["еда"], "price_max": None}, now=NOW
    )
    # date_filter is "any" (timing isn't the point of a food/date/kids question),
    # so a well-rated place should outrank an event that merely happens to have a date.
    assert result[0]["name"] == "top-rated-cafe"


def test_filter_candidates_ranks_records_matching_more_intent_tags_first():
    data = [
        _place("just-active", tags=["активный_отдых"], rating=5),
        _event(
            "active-and-free", "2026-10-01T19:00:00+05:00",
            tags=["активный_отдых", "бесплатно"], price=0,
        ),
    ]
    result = agent.filter_candidates(
        data,
        {"date_filter": "any", "intent_tags": ["активный_отдых", "бесплатно"], "price_max": None},
        now=NOW,
    )
    assert result[0]["name"] == "active-and-free"


def test_parse_intent_returns_valid_json_from_chat_fn():
    def fake_chat(messages, json_mode=False):
        return json.dumps(
            {"date_filter": "weekend", "intent_tags": ["романтика"], "price_max": 5000}
        )

    intent = agent.parse_intent("куда сходить на свидание в выходные", fake_chat)
    assert intent == {
        "date_filter": "weekend",
        "intent_tags": ["романтика"],
        "price_max": 5000,
    }


def test_parse_intent_falls_back_to_defaults_on_malformed_json():
    def fake_chat(messages, json_mode=False):
        return "not json at all"

    intent = agent.parse_intent("что угодно", fake_chat)
    assert intent == {"date_filter": "any", "intent_tags": [], "price_max": None}


def test_parse_intent_drops_tags_outside_the_allowed_vocabulary():
    def fake_chat(messages, json_mode=False):
        return json.dumps(
            {"date_filter": "any", "intent_tags": ["романтика", "made_up_tag"]}
        )

    intent = agent.parse_intent("...", fake_chat)
    assert intent["intent_tags"] == ["романтика"]


def test_generate_answer_sends_only_given_candidates_to_chat_fn():
    captured = {}

    def fake_chat(messages, json_mode=False):
        captured["messages"] = messages
        return "Вот отличное место!"

    candidates = [_place("kofeynya-x")]
    result = agent.generate_answer("где поесть?", candidates, fake_chat)

    assert result == "Вот отличное место!"
    user_message = captured["messages"][-1]["content"]
    assert "kofeynya-x" in user_message
    assert "где поесть?" in user_message


def test_answer_question_orchestrates_intent_parse_then_filter_then_answer():
    data = [_place("romantic-cafe", tags=["романтика"])]

    def fake_chat(messages, json_mode=False):
        if json_mode:
            return json.dumps(
                {"date_filter": "any", "intent_tags": ["романтика"], "price_max": None}
            )
        assert "romantic-cafe" in messages[-1]["content"]
        return "Сходи в romantic-cafe!"

    result = agent.answer_question("куда сходить на свидание?", data, fake_chat, now=NOW)
    assert result == "Сходи в romantic-cafe!"
