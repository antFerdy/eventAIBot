import datetime
import json

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

import agent
import orpo_dataset
from train_orpo import ADAPTER_DIR, BASE_MODEL, pick_dtype

# Held-out: none of these were in the 30 training questions (orpo_pairs.json).
HELD_OUT_QUESTIONS = [
    "Куда сходить с друзьями в субботу?",
    "Посоветуй тихое место, чтобы почитать книгу",
    "Где отметить день рождения?",
]


def generate(model, tokenizer, messages: list[dict], max_new_tokens: int = 300) -> str:
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    output = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=False,
        pad_token_id=pad_id,
    )
    generated = output[0][inputs["input_ids"].shape[1] :]
    return tokenizer.decode(generated, skip_special_tokens=True)


if __name__ == "__main__":
    data = json.load(open("sxodim_data.json"))
    chat = agent.make_ollama_chat()
    now = datetime.datetime.now().astimezone()

    dtype = pick_dtype(
        cuda_available=torch.cuda.is_available(),
        bf16_supported=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=dtype)

    # Resolve retrieval once per question so "before" and "after" answer the
    # exact same prompt -- an Ollama-sampled intent/candidate set could
    # otherwise drift between the two generations and confound the comparison.
    results = []
    for question in HELD_OUT_QUESTIONS:
        intent = agent.parse_intent(question, chat)
        candidates = agent.filter_candidates(data, intent, now=now)
        messages = orpo_dataset.build_messages(question, candidates)
        before = generate(model, tokenizer, messages)
        results.append({"question": question, "messages": messages, "before": before})
        print(f"[before] {question}\n{before}\n")

    tuned_model = PeftModel.from_pretrained(model, ADAPTER_DIR)
    for entry in results:
        after = generate(tuned_model, tokenizer, entry["messages"])
        entry["after"] = after
        print(f"[after] {entry['question']}\n{after}\n")
        del entry["messages"]

    with open("orpo_comparison.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Saved -> orpo_comparison.json")
