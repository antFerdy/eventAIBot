import json

import orpo_dataset


def _place(name):
    return {
        "id": f"place-{name}",
        "type": "place",
        "name": name,
        "category": "Рестораны",
        "tags": ["еда"],
        "description": "desc",
        "address": "addr",
        "date_start": None,
        "price": None,
        "currency": None,
        "rating": 5,
        "url": f"https://sxodim.com/almaty/place/{name}",
        "image": None,
    }


def test_build_messages_includes_question_and_candidate_names():
    candidates = [_place("kofeynya-x")]
    messages = orpo_dataset.build_messages("где поесть?", candidates)

    assert messages[0]["role"] == "system"
    user_content = messages[-1]["content"]
    assert "где поесть?" in user_content
    assert "kofeynya-x" in user_content


def test_build_messages_drops_verbose_fields_not_needed_for_a_recommendation():
    candidates = [_place("kofeynya-x")]
    candidates[0]["url"] = "https://sxodim.com/almaty/place/kofeynya-x"
    candidates[0]["image"] = "https://sxodim.com/uploads/some-very-long-image-url.jpg"
    candidates[0]["id"] = "place-kofeynya-x"

    messages = orpo_dataset.build_messages("где поесть?", candidates)
    user_content = messages[-1]["content"]

    # url/image/id are irrelevant to writing a recommendation and just bloat
    # the training prompt (they made real prompts average ~2300 tokens).
    assert "sxodim.com" not in user_content
    assert "image" not in user_content


def test_format_example_uses_injected_chat_template_fn():
    captured = {}

    def fake_apply_chat_template(messages):
        captured["messages"] = messages
        return "RENDERED_PROMPT"

    example = orpo_dataset.format_example(
        question="где поесть?",
        candidates=[_place("kofeynya-x")],
        chosen="Тёплый ответ!",
        rejected="Сухой ответ.",
        apply_chat_template=fake_apply_chat_template,
    )

    assert example == {
        "prompt": "RENDERED_PROMPT",
        "chosen": "Тёплый ответ!",
        "rejected": "Сухой ответ.",
    }
    assert captured["messages"][0]["role"] == "system"


def test_generate_pairs_calls_warm_and_dry_bootstrap_prompts(monkeypatch):
    import datetime

    data = [_place("kofeynya-x")]
    calls = []

    def fake_chat(messages, json_mode=False):
        calls.append(messages)
        if json_mode:
            return json.dumps({"date_filter": "any", "intent_tags": ["еда"], "price_max": None})
        system = messages[0]["content"]
        if system == orpo_dataset.WARM_BOOTSTRAP_PROMPT:
            return "Тёплый ответ!"
        if system == orpo_dataset.DRY_BOOTSTRAP_PROMPT:
            return "Сухой ответ."
        raise AssertionError("unexpected system prompt")

    now = datetime.datetime(2026, 9, 30, 12, tzinfo=datetime.timezone.utc)
    pairs = orpo_dataset.generate_pairs(["где поесть?"], data, fake_chat, now=now)

    assert len(pairs) == 1
    assert pairs[0]["question"] == "где поесть?"
    assert pairs[0]["chosen"] == "Тёплый ответ!"
    assert pairs[0]["rejected"] == "Сухой ответ."
    assert pairs[0]["candidates"][0]["name"] == "kofeynya-x"


def test_generate_pairs_skips_questions_with_no_candidates(monkeypatch):
    import datetime

    def fake_chat(messages, json_mode=False):
        if json_mode:
            return json.dumps({"date_filter": "today", "intent_tags": [], "price_max": None})
        raise AssertionError("should not generate text with no candidates")

    now = datetime.datetime(2026, 9, 30, 12, tzinfo=datetime.timezone.utc)
    # date_filter "today" with an empty dataset -> no candidates at all
    pairs = orpo_dataset.generate_pairs(["куда сходить сегодня?"], [], fake_chat, now=now)
    assert pairs == []


def test_save_and_load_pairs_round_trip(tmp_path):
    pairs = [
        {"question": "где поесть?", "chosen": "тепло", "rejected": "сухо"},
    ]
    path = tmp_path / "orpo_pairs.json"
    orpo_dataset.save_pairs(pairs, str(path))
    loaded = orpo_dataset.load_pairs(str(path))
    assert loaded == pairs
