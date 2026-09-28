import json
from datetime import datetime, timedelta

import requests

import normalize

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"

ALLOWED_TAGS = sorted({tag for _, tag in normalize.TAGS_BY_KEYWORD} | {"бесплатно"})
ALLOWED_DATE_FILTERS = ("today", "weekend", "week", "any")

TOP_N = 8
MIN_TAG_MATCHES = 3

INTENT_SYSTEM_PROMPT = f"""Ты переводишь вопрос пользователя о том, куда сходить в Алматы, в JSON-фильтр.
Верни ТОЛЬКО JSON вида:
{{"date_filter": "today"|"weekend"|"week"|"any", "intent_tags": [...], "price_max": число или null}}

Допустимые intent_tags (используй только из этого списка, можно несколько или пустой список):
{", ".join(ALLOWED_TAGS)}

date_filter:
- "today" — если спрашивают про сегодня
- "weekend" — если про выходные/субботу/воскресенье
- "week" — если про эту неделю
- "any" — если конкретная дата не важна (используй по умолчанию)

Примеры:
"куда сходить на выходных?" -> {{"date_filter": "weekend", "intent_tags": [], "price_max": null}}
"посоветуй место для свидания" -> {{"date_filter": "any", "intent_tags": ["романтика"], "price_max": null}}
"куда сводить ребенка?" -> {{"date_filter": "any", "intent_tags": ["для_детей"], "price_max": null}}
"какие концерты будут?" -> {{"date_filter": "any", "intent_tags": ["концерт"], "price_max": null}}
"где вкусно поесть?" -> {{"date_filter": "any", "intent_tags": ["еда"], "price_max": null}}
"что-нибудь бесплатное для активного отдыха" -> {{"date_filter": "any", "intent_tags": ["активный_отдых", "бесплатно"], "price_max": null}}"""

ANSWER_SYSTEM_PROMPT = """Ты — дружелюбный гид по Алматы. Пользователь спрашивает, куда сходить.
Тебе дан список подходящих мест и событий в формате JSON. Отвечай ТОЛЬКО на русском, тепло
и по-человечески. Порекомендуй 2-4 варианта СТРОГО ИЗ ЭТОГО СПИСКА — никогда не придумывай
места или события от себя. Для каждой рекомендации укажи название, коротко что это, адрес,
а если есть — дату и цену. Если у записи цена не указана (price отсутствует или null) —
НЕ утверждай, что место платное или бесплатное, просто не упоминай цену.
Если список пуст, честно скажи, что не нашёл подходящего варианта,
и предложи переформулировать вопрос."""


def make_ollama_chat(model: str = OLLAMA_MODEL, url: str = OLLAMA_URL):
    """Return a chat_fn(messages, json_mode=False) -> str backed by a local Ollama server."""

    def chat(messages, json_mode=False):
        payload = {"model": model, "messages": messages, "stream": False}
        if json_mode:
            payload["format"] = "json"
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["message"]["content"]

    return chat


def parse_intent(question: str, chat_fn) -> dict:
    """Ask the LLM for a structured filter, validating its output defensively."""
    raw = chat_fn(
        [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        json_mode=True,
    )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}

    date_filter = parsed.get("date_filter")
    if date_filter not in ALLOWED_DATE_FILTERS:
        date_filter = "any"

    intent_tags = [t for t in (parsed.get("intent_tags") or []) if t in ALLOWED_TAGS]

    price_max = parsed.get("price_max")
    if not isinstance(price_max, (int, float)):
        price_max = None

    return {
        "date_filter": date_filter,
        "intent_tags": intent_tags,
        "price_max": price_max,
    }


def _upcoming_weekend_dates(now: datetime) -> set:
    weekday = now.weekday()  # Mon=0 .. Sun=6
    if weekday == 5:
        saturday = now.date()
    elif weekday == 6:
        saturday = now.date() - timedelta(days=1)
    else:
        saturday = now.date() + timedelta(days=5 - weekday)
    return {saturday, saturday + timedelta(days=1)}


def _date_ok(record: dict, date_filter: str, now: datetime) -> bool:
    if record["date_start"] is None:
        return True  # places aren't time-bound
    dt = datetime.fromisoformat(record["date_start"])
    if date_filter == "today":
        return dt.date() == now.date()
    if date_filter == "weekend":
        return dt.date() in _upcoming_weekend_dates(now)
    if date_filter == "week":
        return now.date() <= dt.date() <= (now + timedelta(days=7)).date()
    return True


def _price_ok(record: dict, price_max) -> bool:
    if price_max is None or record["price"] is None:
        return True
    return record["price"] <= price_max


def _sort_key(record: dict, date_filter: str):
    # When the user cares about timing, a dated event matching that window
    # comes first. Otherwise (the common case — свидание/ребёнок/еда/etc.
    # don't care when), rank by rating so a well-reviewed place isn't pushed
    # below every event merely for having a date at all.
    if date_filter != "any" and record["date_start"] is not None:
        return (0, record["date_start"])
    return (1, -(record.get("rating") or 0))


def filter_candidates(data: list[dict], intent: dict, now: datetime, top_n: int = TOP_N) -> list[dict]:
    """Deterministic retrieval: date + price filter, then prefer tag matches."""
    date_filter = intent.get("date_filter", "any")
    intent_tags = set(intent.get("intent_tags") or [])
    price_max = intent.get("price_max")

    pool = [
        r
        for r in data
        if _date_ok(r, date_filter, now) and _price_ok(r, price_max)
    ]

    def match_count(record):
        return len(intent_tags & set(record["tags"]))

    if intent_tags:
        tag_matches = [r for r in pool if match_count(r) > 0]
        if len(tag_matches) >= MIN_TAG_MATCHES:
            pool = tag_matches

    def key(record):
        base = _sort_key(record, date_filter)
        # A record matching more of the requested tags (e.g. both
        # "активный_отдых" and "бесплатно") should outrank one matching
        # only one of them, even if the single-match record rates higher.
        return (-match_count(record), *base) if intent_tags else base

    return sorted(pool, key=key)[:top_n]


def generate_answer(question: str, candidates: list[dict], chat_fn) -> str:
    context = json.dumps(candidates, ensure_ascii=False, indent=2)
    return chat_fn(
        [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Вопрос: {question}\n\nКандидаты:\n{context}"},
        ]
    )


def answer_question(question: str, data: list[dict], chat_fn, now: datetime | None = None) -> str:
    now = now or datetime.now().astimezone()
    intent = parse_intent(question, chat_fn)
    candidates = filter_candidates(data, intent, now=now)
    return generate_answer(question, candidates, chat_fn)
