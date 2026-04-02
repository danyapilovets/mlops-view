#!/usr/bin/env python3
"""Evaluate a fine-tuned (PEFT) causal LM; log to MLflow; print XCom-safe JSON."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from pathlib import Path
from typing import Any

import mlflow
import torch
from datasets import Dataset, load_dataset
from peft import PeftConfig, PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate fine-tuned model; output JSON for XCom")
    p.add_argument("--model-path", required=True, type=Path, help="Adapter dir or merged model path")
    p.add_argument(
        "--dataset-path",
        required=True,
        help="Dataset with a test split or single split for eval",
    )
    p.add_argument(
        "--mlflow-tracking-uri",
        default=None,
        help="Overrides MLFLOW_TRACKING_URI",
    )
    p.add_argument("--text-column", default="text")
    p.add_argument("--max-seq-length", type=int, default=512)
    p.add_argument("--split", default="test", help="Split name, or 'train' if only one split")
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--mlflow-run-name", default="evaluate", help="Optional MLflow run name")
    return p.parse_args()


def load_eval_dataset(path: str, split: str) -> Dataset:
    file_path = Path(path)
    if file_path.is_dir() and (file_path / "dataset_info.json").exists():
        from datasets import load_from_disk

        ds_dict = load_from_disk(str(file_path))
        if split in ds_dict:
            return ds_dict[split]
        if len(ds_dict) == 1:
            return next(iter(ds_dict.values()))
        raise ValueError(f"Split '{split}' not found. Keys: {list(ds_dict.keys())}")

    if file_path.is_file():
        suf = file_path.suffix.lower()
        if suf == ".json":
            d = load_dataset("json", data_files=str(file_path))
        elif suf in (".jsonl", ".ndjson"):
            d = load_dataset("json", data_files=str(file_path))
        elif suf == ".csv":
            d = load_dataset("csv", data_files=str(file_path))
        else:
            raise ValueError(f"Unsupported file: {suf}")
        if split in d:
            return d[split]
        return d["train"]

    d = load_dataset(path)
    if split in d:
        return d[split]
    return d["train"]


@torch.inference_mode()
def compute_eval_loss(
    model: Any,
    tokenizer: Any,
    dataset: Dataset,
    text_column: str,
    max_length: int,
    batch_size: int,
) -> float:
    if text_column not in dataset.column_names:
        raise ValueError(f"Column '{text_column}' missing. Got: {dataset.column_names}")

    device = next(model.parameters()).device
    total_loss = 0.0
    total_tokens = 0

    for i in range(0, len(dataset), batch_size):
        batch = dataset[i : i + batch_size]
        texts = batch[text_column]
        enc = tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_length,
        )
        enc = {k: v.to(device) for k, v in enc.items()}
        labels = enc["input_ids"].clone()
        out = model(**enc, labels=labels)
        loss = out.loss
        if loss is None:
            raise RuntimeError("Model did not return loss")
        n = (labels != tokenizer.pad_token_id).sum().item()
        total_loss += loss.item() * max(n, 1)
        total_tokens += max(n, 1)

    if total_tokens == 0:
        raise RuntimeError("No tokens in evaluation batch")
    return total_loss / total_tokens


def main() -> int:
    args = parse_args()
    model_path = args.model_path.resolve()
    if not model_path.exists():
        logger.error("Model path does not exist: %s", model_path)
        return 1

    tracking = args.mlflow_tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")

    logger.info("Loading tokenizer from %s", model_path)
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    adapter_config = model_path / "adapter_config.json"
    if adapter_config.exists():
        logger.info("Loading base model with PEFT adapter")
        cfg = PeftConfig.from_pretrained(str(model_path))
        base = AutoModelForCausalLM.from_pretrained(
            cfg.base_model_name_or_path,
            torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
        )
        model = PeftModel.from_pretrained(base, str(model_path))
    else:
        logger.info("Loading full model from %s", model_path)
        model = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
        )

    model.eval()

    logger.info("Loading dataset %s (split=%s)", args.dataset_path, args.split)
    try:
        eval_ds = load_eval_dataset(args.dataset_path, args.split)
    except Exception as e:
        logger.exception("Failed to load dataset: %s", e)
        return 1

    try:
        avg_loss = compute_eval_loss(
            model,
            tokenizer,
            eval_ds,
            args.text_column,
            args.max_seq_length,
            args.batch_size,
        )
    except Exception as e:
        logger.exception("Evaluation failed: %s", e)
        return 1

    perplexity = float(math.exp(avg_loss)) if avg_loss < 100 else float("inf")

    payload: dict[str, Any] = {
        "loss": round(avg_loss, 6),
        "perplexity": round(perplexity, 6) if math.isfinite(perplexity) else None,
        "num_examples": len(eval_ds),
        "model_path": str(model_path),
    }

    if tracking:
        os.environ["MLFLOW_TRACKING_URI"] = tracking
        try:
            with mlflow.start_run(run_name=args.mlflow_run_name):
                mlflow.log_metric("eval_loss", avg_loss)
                if math.isfinite(perplexity):
                    mlflow.log_metric("perplexity", perplexity)
                mlflow.log_param("model_path", str(model_path))
        except Exception as e:
            logger.warning("MLflow logging failed (continuing): %s", e)

    # Single-line JSON for Airflow XCom / orchestration
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
