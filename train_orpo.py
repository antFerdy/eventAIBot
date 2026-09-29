import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl.experimental.orpo import ORPOConfig, ORPOTrainer

import orpo_dataset

BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
ADAPTER_DIR = "orpo_adapter"


def build_dataset(pairs: list[dict], tokenizer) -> Dataset:
    def apply_template(messages):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    examples = [
        orpo_dataset.format_example(p["question"], p["candidates"], p["chosen"], p["rejected"], apply_template)
        for p in pairs
    ]
    return Dataset.from_list(examples)


def make_lora_config() -> LoraConfig:
    return LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type="CAUSAL_LM",
    )


def make_training_config(output_dir: str = ADAPTER_DIR) -> ORPOConfig:
    return ORPOConfig(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        num_train_epochs=1,
        max_length=1024,
        learning_rate=1e-4,
        logging_steps=1,
        report_to=[],
        remove_unused_columns=False,
        save_strategy="no",
    )


if __name__ == "__main__":
    pairs = orpo_dataset.load_pairs("orpo_pairs.json")
    print(f"Loaded {len(pairs)} training pairs")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.float32)
    dataset = build_dataset(pairs, tokenizer)

    trainer = ORPOTrainer(
        model=model,
        args=make_training_config(),
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=make_lora_config(),
    )
    trainer.train()
    trainer.save_model(ADAPTER_DIR)
    print(f"Saved LoRA adapter -> {ADAPTER_DIR}")
