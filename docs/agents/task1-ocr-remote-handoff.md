# Task 1 OCR remote-worker handoff

## Status and ownership

This is a historical one-time preprocessing handoff, not an active runtime service.
The remote worker may produce immutable OCR/canonical-IR artifacts only. The primary
FastAPI ingestion owner validates hashes and provenance, applies legal parsing/evidence
gates, persists accepted application data through Supabase REST/Auth where applicable,
then indexes approved legal provisions into Qdrant hybrid retrieval. The single
OpenRouter generator is never part of OCR.

## Objective

Run OCR preprocessing for the Task 1 corpus PDFs on the RTX 3050 machine and return
immutable artifacts to the primary workstation. Do not change legal verification semantics.

## Input PDFs

The primary workstation stores the input PDFs in the handoff staging directory:

```text
/tmp/vnlrag-task1-pdfs/
```

Transfer only the staged inputs. SHA-256 values in the matching `data/manifests/` files
are authoritative; recompute and compare before processing. Never commit PDFs or model weights.

## Runtime constraints

Remote machine: RTX 3050, stronger CPU than the primary workstation.

Use one worker process. GPU use is optional and must follow a smoke test confirming the
selected OCR runtime initializes on the RTX 3050. Keep batch size small (1–2 pages).
Do not run RAGFlow, LightRAG, RAG-Anything, agents, LangGraph, external retrieval, Redis,
MinIO, a local LLM, or the application API as part of this job.

This handoff records the historical PaddleOCR/VietOCR experiment. The active scan policy
in `docs/parser_router.yaml` uses Tesseract Vietnamese; whichever OCR artifact is produced
must identify its parser/version/device in provenance and still pass the same gates.

Recommended isolated environment for the historical PaddleOCR/VietOCR worker:

```bash
python3.11 -m venv /tmp/vnlrag-ocr-venv
source /tmp/vnlrag-ocr-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install 'paddleocr==3.3.0' 'vietocr==0.3.13' PyMuPDF Pillow opencv-python
```

Install a PaddlePaddle build compatible with the remote NVIDIA driver/CUDA runtime
according to official instructions. Keep model weights outside the repository, record
their URL/version/SHA-256, and never disable TLS verification.

## Processing contract

For each PDF:

1. Verify the source SHA-256 against its manifest.
2. Detect whether a usable text layer exists.
3. For scanned pages, render at 250–300 DPI.
4. Run the configured Vietnamese-capable OCR engine.
5. Use any secondary recognizer only for low-confidence lines or explicitly selected difficult
   samples; do not run it blindly over every line.
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
  "parser": "OCR_ENGINE_AND_VERSION",
  "parser_version": "<record exact package/model versions>",
  "ocr_device": "cpu|gpu",
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

- all document state entries are terminal;
- every PDF hash matches its manifest;
- page coverage equals the PDF page count;
- every page has a JSON artifact or an explicit quarantine record;
- `canonical_ir.json` validates against `document-ir-v2`;
- `samples.json` exists for every input PDF;
- `run.json` records package/model/device versions and output hash;
- no secrets are present in logs or artifacts.

Transfer the entire output directory back to the primary workstation. The primary agent
independently validates hashes, inspects samples, persists accepted IR/provisions, runs
legal/evidence gates, embeds, and indexes into Qdrant. Do not mark Task 1 done from OCR
completion alone.

## Do not do

- Do not commit PDFs, model weights, `.env`, credentials, or caches.
- Do not mark quarantined pages as valid.
- Do not introduce another database or replace Supabase application persistence/Qdrant retrieval.
- Do not change citation IDs or legal relation semantics.
- Do not claim evaluation metrics without a real provider-backed run.
