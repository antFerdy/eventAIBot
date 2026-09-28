# Sxodim Agent — Design Spec

Date: 2026-09-28
Status: Approved for planning

## 1. Purpose

Build a fully local AI agent that scrapes sxodim.com/almaty (events, places,
restaurants, entertainment) and answers natural-language questions in Russian
about where to go in Almaty ("Куда сходить на выходных?", "Посоветуй место
для свидания", "Куда сводить ребенка?", etc.), grounding every recommendation
in real scraped data — no hallucinated venues.

This satisfies ТЗ #2 from `prd.md`: parsed data file, structured JSON,
question-answering agent, clean/understandable code, plus a full ORPO
fine-tuning bonus for friendlier responses.

## 2. Constraints

- **Fully local**: no external paid APIs (no OpenAI/Firecrawl keys). Uses
  Ollama (already has `qwen2.5-7b-instruct` pulled) for the agent, and a
  separate small HuggingFace model for ORPO training.
- **Minimum magic**: prefer explicit, inspectable steps over frameworks
  (no LangChain/LlamaIndex, no vector DB). Every LLM call has a clear,
  narrow job.
- **Reproducible**: scraping happens once, offline, into a JSON file. The
  agent never hits the network at question-answering time.
- Target machine: Apple M4 Pro, 24GB RAM (MPS backend for ORPO training).

## 3. Key discovery driving the design

sxodim.com's event and place detail pages (`/almaty/event/<slug>`,
`/almaty/place/<slug>`) embed `schema.org` JSON-LD directly in
server-rendered HTML:

- Events (`@type: Event`): `name`, `startDate`, `location.address`,
  `offers.price`/`priceCurrency`, `description`.
- Places (`@type: LocalBusiness`): `name`, `address`, `telephone`,
  `aggregateRating`.
- Both pages also carry a `BreadcrumbList` giving the item's category
  (e.g. "Концерты", "Кофейни").

Because this structured data already exists, scraping does not need
Crawl4AI/Firecrawl/headless browsers — plain `requests` + JSON-LD
extraction is sufficient, faster, and more reliable than LLM-based
extraction from raw text.

## 4. Pipeline

```
1. Scrape   → sxodim_raw.json    (raw JSON-LD per event/place, deduped)
2. Tag      → sxodim_data.json   (normalized schema + LLM semantic tags)
3. Agent    → retrieval (filters) + LLM-generated answer
4. ORPO     → bonus: friendliness fine-tuning demo (separate model)
```

### 4.1 Scraping

- HTTP via `requests`, JSON-LD extraction via regex + `json.loads`
  (no BeautifulSoup dependency needed for this specific job, but may use
  it if link discovery gets messy).
- **Event URL discovery**: paginate `https://sxodim.com/almaty/afisha?page=N`.
  Verified live: this listing has exactly **9 pages**, `page=10` returns
  zero results, and the `date_from`/`date_to` query params are ignored by
  the site (no effect on results) — so no separate `events/week`,
  `events/weekend`, category listings, or date-range queries are needed.
  Total: **139 unique events**, all of them (no cap needed — it's already
  a small, complete set).
- **Place URL discovery**: the general `places?page=N` listing has **119
  pages** (~2260 places total) but is dominated by a few categories
  (verified live: `cafe` alone is 77 pages / ~1223 places, `restaurants`
  23 pages, `bars` 15 pages) while others are tiny (`dlja-detej` — "for
  kids" — only 2 pages / ~14 places, `museums` similarly small). Taking
  the first N pages of the *general* listing would skew heavily toward
  whatever the default sort surfaces and risks missing small-but-relevant
  categories entirely — including `dlja-detej`, which directly matters
  for the required "куда сводить ребёнка" question.
  Instead: paginate the first **2 pages of each of the 22 category
  listings** (`places/<category>?page=1,2` — categories are: anticafe,
  aquapark, bars, beauty-health, biblioteki-, cafe, cinema, coffee-house,
  countryside, coworkings, dlja-detej, education, entertainment, hotels,
  karaoke, konditerskaya, museums, parks, prokat-snaryazheniya,
  recreation, restaurants, theatres), then dedupe by slug. This fully
  captures small categories and takes a representative slice of large
  ones instead of an arbitrary sequential cut — expect roughly **500-650
  unique places** after dedup. Documented explicitly in the notebook as
  a deliberate, category-balanced scope cap, not silent truncation.
- Polite delay (~0.3s) between requests.
- Fetch each event/place detail page, extract the `Event` or
  `LocalBusiness` JSON-LD block + breadcrumb category.
- Output: `sxodim_raw.json` — list of raw extracted records, printed
  fragment shown in notebook as required deliverable evidence.

### 4.2 Structuring + tagging

- Normalize raw records into one schema:
  ```json
  {
    "id": "event-abzal-uteshovty-koncerti",
    "type": "event | place",
    "name": "...",
    "category": "Концерты",
    "tags": ["концерт", "музыка"],
    "description": "...",
    "address": "...",
    "date_start": "2026-10-07T16:00:00+05:00",
    "price": 12000,
    "currency": "KZT",
    "rating": null,
    "url": "https://...",
    "image": "https://..."
  }
  ```
- Tags come from two sources, not LLM-only:
  - **Site-derived tags** (free, reliable): the place category slug used
    to discover the URL (e.g. `dlja-detej` → `для_детей`,
    `restaurants`/`cafe` → `еда`, event breadcrumb category e.g.
    "Концерты" → `концерт`) is mapped directly via a small fixed
    dictionary — no LLM guesswork for things the site already told us.
  - **LLM-derived tags** (one Ollama call per record, `qwen2.5-7b-instruct`,
    constrained JSON output): fills in cross-cutting tags the site
    doesn't label directly and that matter for the ТЗ's example
    questions — `романтика` (date-spot vibe), `новое` (recently added),
    `бесплатно` (price == 0 already covers most of this, LLM only for
    ambiguous cases). This is the "structure text into events" step
    required by the ТЗ, layered on top of the JSON-LD + category structure.
- Output: `sxodim_data.json` — the required deliverable.

### 4.3 Agent (retrieval + generation, no vector DB)

Two narrow, explicit LLM calls per question, with deterministic Python in
between:

1. **Intent parsing** (LLM call #1): user question → constrained JSON
   `{date_filter: today|weekend|week|any, intent_tags: [...], price_max: number|null}`.
2. **Retrieval** (plain Python, no LLM): filter `sxodim_data.json` by
   `date_filter` against `date_start`, by `intent_tags` against `tags`,
   by `price_max`; fall back to keyword substring scoring over
   `name`+`description` if filters return too few results. Take top 5-8
   candidates.
3. **Answer generation** (LLM call #2): candidates + original question →
   friendly Russian answer that only references the given candidates
   (system prompt explicitly forbids inventing venues).

### 4.4 ORPO bonus (full fine-tuning, not just prompting)

- Runs on a **separate small HuggingFace model**
  (`Qwen/Qwen2.5-1.5B-Instruct`), not the Ollama 7B that powers the main
  agent — keeps the core agent's reliability decoupled from the
  fine-tuning experiment.
- Preference dataset (~40-60 pairs): for a set of (question, retrieved
  context) pairs, generate `rejected` (dry/formal answer) and `chosen`
  (warm, friendly answer with emoji/tone) via prompting, then train with
  `TRL`'s `ORPOTrainer` + LoRA (`peft`).
- Notebook shows a before/after comparison: same prompt → base model
  answer vs ORPO-tuned model answer.
- Separate Python 3.12 virtualenv (not system Python 3.14 — too new for
  reliable `torch`/`trl`/`transformers` wheel availability) with `torch`
  (MPS backend), `transformers`, `trl`, `peft`, `datasets`.

## 5. Deliverables

```
sxodim_agent.ipynb    — full pipeline notebook, run with outputs, sections:
                         scrape → tag → agent → demo (6+ questions) → ORPO bonus
sxodim_data.json      — final structured dataset
agent_examples.md     — 5+ Q&A dialogue examples (ТЗ's example questions + extras)
sxodim_raw.json       — intermediate raw JSON-LD (supporting evidence, not required but useful)
```

## 6. Testing / verification

- Scraper: assert non-empty results, spot-check a handful of records
  against the live pages fetched during design (already verified
  manually: JSON-LD present and parseable for both event and place pages).
- Tagging: spot-check tag assignment for a few known items.
- Agent: run all 6 ТЗ example questions + a few edge cases (no-match
  query) and confirm answers only cite real dataset entries.
- ORPO: qualitative before/after comparison on held-out prompts (not
  used in training).

## 7. Out of scope

- Live/on-demand scraping per user question.
- Vector embeddings / vector database / LangChain / LlamaIndex.
- Paid APIs (OpenAI, Firecrawl).
- Exhaustive place scraping (full ~2260 places across 119 general-listing
  pages, or all of `cafe`'s 77 pages) — capped by design to 2 pages per
  category instead.
