import json

import agent

# The system prompt the ORPO-tuned model will actually see at deployment —
# the same one the main (untrained) agent uses. Only the *completions* used
# to teach the contrast (chosen vs rejected) come from different bootstrap
# prompts; what the model is trained to complete is this real prompt.
DEPLOY_SYSTEM_PROMPT = agent.ANSWER_SYSTEM_PROMPT

DRY_BOOTSTRAP_PROMPT = """Ты — справочная служба. Тебе дан список кандидатов в формате JSON —
это только источник фактов, а не то, что нужно вернуть пользователю. Твой ответ должен быть
ОБЫЧНЫМ СВЯЗНЫМ ТЕКСТОМ на русском языке — не JSON, не таблица, не сырые данные. Пиши сухо,
формально, канцелярским языком, без эмоций и эмодзи. Пронумерованным списком из коротких
предложений перечисли 2-3 варианта строго из кандидатов: название, адрес, при наличии — дата
и цена. Никаких вводных фраз, пожеланий или личного мнения — только факты в виде предложений."""

WARM_BOOTSTRAP_PROMPT = """Ты — тёплый, увлечённый гид по Алматы, который обожает свой город
и хочет, чтобы у собеседника было отличное настроение. Отвечай живо и по-дружески, используй
2-4 эмодзи и обращайся на "ты". Порекомендуй 2-3 варианта строго из списка кандидатов (JSON) —
никогда не выдумывай ничего от себя, включай короткий личный комментарий, почему это классный
выбор, и заверши тёплым пожеланием."""


_COMPACT_FIELDS = ("name", "category", "address", "date_start", "price", "currency", "rating")


def _compact_candidate(record: dict) -> dict:
    """Keep only the fields a recommendation actually needs. Dropping
    url/image/id/description/type cut real training prompts from ~2300
    tokens/example to a fraction of that on MPS."""
    return {k: record[k] for k in _COMPACT_FIELDS if record.get(k) is not None}


def build_messages(question: str, candidates: list[dict]) -> list[dict]:
    context = json.dumps([_compact_candidate(c) for c in candidates], ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": DEPLOY_SYSTEM_PROMPT},
        {"role": "user", "content": f"Вопрос: {question}\n\nКандидаты:\n{context}"},
    ]


def format_example(question, candidates, chosen, rejected, apply_chat_template) -> dict:
    """Build one TRL-shaped {prompt, chosen, rejected} training example.

    `apply_chat_template` is injected as messages -> str so this stays
    testable without loading a real tokenizer.
    """
    messages = build_messages(question, candidates)
    return {
        "prompt": apply_chat_template(messages),
        "chosen": chosen,
        "rejected": rejected,
    }


def generate_pairs(questions: list[str], data: list[dict], chat_fn, now) -> list[dict]:
    """For each question, retrieve real candidates then bootstrap a warm
    (chosen) and dry (rejected) answer from the same chat_fn/candidates.
    Questions with no matching candidates are skipped — there's nothing
    grounded to write a training pair about.
    """
    pairs = []
    for question in questions:
        intent = agent.parse_intent(question, chat_fn)
        candidates = agent.filter_candidates(data, intent, now=now)
        if not candidates:
            continue
        context = json.dumps(candidates, ensure_ascii=False, indent=2)
        user_message = {"role": "user", "content": f"Вопрос: {question}\n\nКандидаты:\n{context}"}
        chosen = chat_fn([{"role": "system", "content": WARM_BOOTSTRAP_PROMPT}, user_message])
        rejected = chat_fn([{"role": "system", "content": DRY_BOOTSTRAP_PROMPT}, user_message])
        pairs.append(
            {
                "question": question,
                "candidates": candidates,
                "chosen": chosen,
                "rejected": rejected,
            }
        )
    return pairs


def save_pairs(pairs: list[dict], path: str = "orpo_pairs.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)


def load_pairs(path: str = "orpo_pairs.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
