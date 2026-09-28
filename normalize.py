import json

# Deterministic category -> tag mapping, no LLM. Checked as a case-insensitive
# substring match against the record's category string; a category can match
# several rules and pick up several distinct tags (e.g. "Антикафе" matches
# both "антикафе" and "кафе").
TAGS_BY_KEYWORD = [
    ("концерт", "концерт"),
    ("тур", "активный_отдых"),
    ("спорт", "активный_отдых"),
    ("детям", "для_детей"),
    ("детей", "для_детей"),
    ("ресторан", "еда"),
    ("кафе", "еда"),
    ("кофейн", "еда"),
    ("кондитерск", "еда"),
    ("дегустаци", "еда"),
    ("театр", "искусство"),
    ("спектакл", "искусство"),
    ("музе", "искусство"),
    ("кино", "искусство"),
    ("фестивал", "искусство"),
    ("библиотек", "искусство"),
    ("бар", "ночная_жизнь"),
    ("караоке", "ночная_жизнь"),
    ("stand up", "ночная_жизнь"),
    ("standup", "ночная_жизнь"),
    ("spa", "романтика"),
    ("парк", "активный_отдых"),
    ("антикафе", "активный_отдых"),
    ("аквапарк", "активный_отдых"),
    ("бассейн", "активный_отдых"),
    ("активный отдых", "активный_отдых"),
    ("прокат снаряжения", "активный_отдых"),
    ("загородный отдых", "активный_отдых"),
    ("развлечен", "активный_отдых"),
    ("мастер-класс", "образование"),
    ("образование", "образование"),
    ("конференци", "образование"),
    ("школ", "образование"),
    ("конкурс", "активный_отдых"),
]


def slug_from_url(url: str, kind: str) -> str:
    """Derive a stable id like 'event-<slug>' from a detail-page URL."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return f"{kind}-{slug}"


def derive_tags(category: str | None, price) -> list[str]:
    """Deterministic tags from the category string and price — no LLM."""
    tags = set()
    if category:
        lowered = category.lower()
        for keyword, tag in TAGS_BY_KEYWORD:
            if keyword in lowered:
                tags.add(tag)
    if price == 0:
        tags.add("бесплатно")
    return sorted(tags)


def normalize_record(raw: dict) -> dict:
    """Add `id` and `tags` to a raw scraper record; keep every other field."""
    record = dict(raw)
    record["id"] = slug_from_url(raw["url"], raw["type"])
    record["tags"] = derive_tags(raw.get("category"), raw.get("price"))
    return record


def normalize_all(raw_records: list[dict]) -> list[dict]:
    """Normalize every record, dropping duplicates by id."""
    seen = set()
    normalized = []
    for raw in raw_records:
        record = normalize_record(raw)
        if record["id"] in seen:
            continue
        seen.add(record["id"])
        normalized.append(record)
    return normalized


def save_data(records: list[dict], path: str = "sxodim_data.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
