"""Prepare cached multilingual-E5 weights for Paddle GPU inference."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from paddlenlp.transformers import RobertaModel

REPO_ROOT = Path(__file__).resolve().parents[2]
HF_MODEL = (
    Path.home() / ".cache/huggingface/hub/models--intfloat--multilingual-e5-base/snapshots/"
    "d128750597153bb5987e10b1c3493a34e5a4502a"
)
OUTPUT = REPO_ROOT / "data/models/multilingual-e5-base-paddle"


def main() -> None:
    if not (HF_MODEL / "config.json").is_file() or not (HF_MODEL / "model.safetensors").is_file():
        raise RuntimeError(f"local Hugging Face model missing: {HF_MODEL}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    config = json.loads((HF_MODEL / "config.json").read_text(encoding="utf-8"))
    config.update(
        {"model_type": "roberta", "architectures": ["RobertaModel"], "type_vocab_size": 1}
    )
    (OUTPUT / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(HF_MODEL / "sentencepiece.bpe.model", OUTPUT / "sentencepiece.bpe.model")
    shutil.copy2(HF_MODEL / "tokenizer.json", OUTPUT / "tokenizer.json")
    shutil.copy2(HF_MODEL / "tokenizer_config.json", OUTPUT / "tokenizer_config.json")
    shutil.copy2(HF_MODEL / "special_tokens_map.json", OUTPUT / "special_tokens_map.json")
    shutil.copy2(HF_MODEL / "model.safetensors", OUTPUT / "model.safetensors")
    RobertaModel.from_pretrained(str(OUTPUT), convert_from_torch=True)
    (OUTPUT / "model.safetensors").unlink(missing_ok=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
