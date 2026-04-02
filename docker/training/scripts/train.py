#!/usr/bin/env python3
"""Fine-tune a causal LM with PEFT/LoRA, HF Trainer, and MLflow logging."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

import mlflow
import torch
from datasets import Dataset, load_dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PEFT/LoRA fine-tuning with HF Trainer")
    parser.add_argument("--model-name", required=True, help="Base model id or local path")
    parser.add_argument(
        "--dataset-path",
        required=True,
        help="HF dataset name, JSON/JSONL/CSV file, or directory for load_from_disk",
    )
    parser.add_argument("--output-dir", required=True, type=Path, help="Where to save the adapter")
    parser.add_argument("--num-epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument(
        "--mlflow-tracking-uri",
        default=None,
        help="Overrides MLFLOW_TRACKING_URI if set",
    )
    parser.add_argument("--mlflow-experiment", default=None, help="MLflow experiment name")
    parser.add_argument("--text-column", default="text", help="Column name for LM text")
    parser.add_argument("--max-seq-length", type=int, default=512)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    return parser.parse_args()


def load_raw_dataset(path: str) -> Dataset:
    p = Path(path)
    if p.is_dir() and (p / "dataset_info.json").exists():
        from datasets import load_from_disk

        return load_from_disk(str(p))
    if p.is_file():
        suffix = p.suffix.lower()
        if suffix == ".json":
            return load_dataset("json", data_files=str(p))["train"]
        if suffix in (".jsonl", ".ndjson"):
            return load_dataset("json", data_files=str(p))["train"]
        if suffix == ".csv":
            return load_dataset("csv", data_files=str(p))["train"]
        raise ValueError(f"Unsupported file type: {suffix}")
    return load_dataset(path, split="train")


def tokenize_dataset(
    ds: Dataset,
    tokenizer: Any,
    text_column: str,
    max_length: int,
) -> Dataset:
    if text_column not in ds.column_names:
        raise ValueError(
            f"Column '{text_column}' not in dataset. Available: {ds.column_names}",
        )

    def _tok(batch: dict[str, list[Any]]) -> dict[str, Any]:
        return tokenizer(
            batch[text_column],
            truncation=True,
            max_length=max_length,
            padding=False,
        )

    return ds.map(_tok, batched=True, remove_columns=ds.column_names)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tracking = args.mlflow_tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
    if tracking:
        os.environ["MLFLOW_TRACKING_URI"] = tracking
    if args.mlflow_experiment:
        mlflow.set_experiment(args.mlflow_experiment)

    logger.info("Loading tokenizer and model: %s", args.model_name)
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
        trust_remote_code=True,
    )

    lora = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    logger.info("Loading dataset from %s", args.dataset_path)
    raw = load_raw_dataset(args.dataset_path)
    tokenized = tokenize_dataset(raw, tokenizer, args.text_column, args.max_seq_length)

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    report_to: list[str] = []
    if tracking or os.environ.get("MLFLOW_TRACKING_URI"):
        report_to.append("mlflow")

    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.num_epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        logging_steps=10,
        save_strategy="epoch",
        bf16=torch.cuda.is_available(),
        report_to=report_to,
        gradient_accumulation_steps=1,
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized,
        data_collator=data_collator,
        tokenizer=tokenizer,
    )

    logger.info("Starting training")
    trainer.train()
    logger.info("Saving adapter to %s", args.output_dir)
    trainer.model.save_pretrained(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))

    return 0


if __name__ == "__main__":
    sys.exit(main())
