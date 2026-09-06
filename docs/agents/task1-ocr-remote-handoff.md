# Task 1 OCR remote-worker handoff

## Objective

Run the one-time OCR preprocessing for the 13 Task 1 PDFs on the stronger RTX 3050 machine. Return immutable OCR/Canonical IR artifacts to the primary workstation. Do not change legal verification semantics.

## Input PDFs

The primary workstation currently stores the 13 PDFs at:

```text
/tmp/vnlrag-task1-pdfs/
```

Transfer this directory to the remote machine. The exact PDF SHA-256 values are authoritative in the matching files under `data/manifests/`. Recompute and compare before processing. Never commit the PDFs or model weights.

## Runtime constraints

Remote machine: RTX 3050, stronger CPU than the primary workstation.

Use one worker process. Use GPU only after a smoke test confirms the selected Paddle runtime can initialize on the RTX 3050. Keep batch size small (1–2 pages). Do not run RAGFlow, LightRAG, RAG-Anything, or a local LLM as part of this job.

Recommended isolated environment:

```bash
python3.11 -m venv /tmp/vnlrag-ocr-venv
source /tmp/vnlrag-ocr-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install 'paddleocr==3.3.0' 'vietocr==0.3.13' PyMuPDF Pillow opencv-python
```

Install a PaddlePaddle build compatible with the remote NVIDIA driver/CUDA runtime according to the official PaddleOCR installation instructions. Do not copy the primary workstation's CPU-only Torch/Paddle environment blindly.

VietOCR model weights must be downloaded outside the repository. Record the URL, version, and SHA-256 in the output manifest. Do not disable TLS verification in the worker; if `vocr.vn` certificate validation fails, obtain the public artifact through a trusted verified source and record its checksum.

## Processing contract

For each PDF:

1. Verify the source SHA-256 against its manifest.
2. Detect whether a usable text layer exists.
3. For scanned pages, render at 250–300 DPI.
4. Run PaddleOCR detection/recognition using a Vietnamese-capable model.
5. Use VietOCR only for low-confidence detected lines or explicitly selected difficult samples; do not run it blindly over every line.
6. Preserve page order and reading order.
7. Write one page result atomically before starting the next page.
8. Resume from the checkpoint after interruption.
9. Put low-confidence/empty/structurally ambiguous lines in `quarantine.json`; never silently discard them.
10. Do not mark a PDF accepted solely because OCR completed.

## Required output layout

```text
/tmp/vnlrag-task1-ocr-result/
├── state.json
├── run.json
├── manifests/
│   └── <document_id>.json
├── documents/
│   └── <document_id>/
│       ├── pages/
│       │   ├── page-0001.json
│       │   └── ...
│       ├── checkpoint.json
│       ├── canonical_ir.json
│       ├── quarantine.json
│       ├── samples.json
│       └── sha256.json
└── logs/
    └── worker.log
```

Each page JSON must contain:

```json
{
  "document_id": "nd-166-2024",
  "page_number": 1,
  "source_pdf_sha256": "<64 hex characters>",
  "parser": "PADDLEOCR_VIETOCR",
  "parser_version": "paddleocr-3.3.0+vietocr-0.3.13",
  "ocr_device": "gpu",
  "lines": [
    {
      "text": "...",
      "bbox": [0.1, 0.2, 0.8, 0.24],
      "detection_confidence": 0.98,
      "recognition_confidence": 0.94,
      "reading_order": 0,
      "source_image": "pages/page-0001.jpg"
    }
  ]
}
```

Coordinates are normalized to `[left, top, right, bottom]` in `[0, 1]` with a top-left origin. Keep original polygons and model metadata in the same artifact or an adjacent provenance field.

## Sample review artifact

For every PDF, sample the first, middle, and last page. `samples.json` must record:

- page number;
- source image path;
- OCR text excerpt;
- detected legal headings (`Điều`, `Khoản`, `Điểm`);
- important numbers/dates;
- confidence summary;
- reviewer: `Phuc Truong <phuctruong@student>`;
- review timestamp in UTC;
- decision: `ACCEPTED`, `QUARANTINED`, or `REJECTED`;
- notes for any mismatch.

A sample review does not authorize inventing text. If a page is unreadable, keep it quarantined and report it.

## Detached launch

Run from a persistent terminal/session on the remote machine:

```bash
mkdir -p /tmp/vnlrag-task1-ocr-result/logs
nohup env PYTHONPATH=backend \
  VIETOCR_WEIGHTS=/absolute/path/to/vgg_transformer.pth \
  python backend/scripts/run_hybrid_ocr_batch.py \
  --input /absolute/path/to/vnlrag-task1-pdfs \
  --output /tmp/vnlrag-task1-ocr-result \
  > /tmp/vnlrag-task1-ocr-result/logs/worker.log 2>&1 < /dev/null &
echo $! > /tmp/vnlrag-task1-ocr-result/worker.pid
```

The command must not use an application-level document timeout. Checkpointing, not a timeout, controls recovery. Stop only on explicit operator intervention, fatal hardware/system errors, or completed processing.

## Completion gate

The remote worker is complete only when:

- all 13 `state.json` document entries are terminal;
- every PDF hash matches its manifest;
- page coverage equals the PDF page count;
- every page has a JSON artifact or an explicit quarantine record;
- `canonical_ir.json` validates against `document-ir-v2`;
- `samples.json` exists for all 13 PDFs;
- `run.json` records package/model/device versions and output hash;
- no secrets are present in logs or artifacts.

Transfer the entire output directory back to the primary workstation. The primary agent will independently validate hashes, inspect samples, persist IR/provisions, run legal gates, embed, and index. Do not mark Task 1 Done from the remote OCR result alone.

## Do not do

- Do not commit PDFs, model weights, `.env`, credentials, or caches.
- Do not mark quarantined pages as valid.
- Do not replace PostgreSQL/Qdrant with a new database.
- Do not change citation IDs or legal relation semantics.
- Do not claim evaluation metrics without a real provider-backed run.
