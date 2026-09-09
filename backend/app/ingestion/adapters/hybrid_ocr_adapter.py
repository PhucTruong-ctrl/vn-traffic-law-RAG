"""PaddleOCR detection + VietOCR recognition adapter for scanned legal PDFs."""

from __future__ import annotations

import json
import os
import re

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from PIL import Image

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage

IR_SCHEMA_VERSION = "document-ir-v2"
PARSER_NAME = "PADDLEOCR"
PARSER_VERSION = "paddleocr-3.3.0"
VIETOCR_PARSER_NAME = "PADDLEOCR_VIETOCR"
VIETOCR_PARSER_VERSION = "paddleocr-3.3.0+vietocr-0.3.13"
OCR_MIN_RECOGNITION_CONFIDENCE = 0.80
OCR_LINE_MERGE_MAX_GAP = 0.03
OCR_LINE_MERGE_MIN_OVERLAP = 0.5


def _deduplicate_ocr_lines(lines: list[OCRLine]) -> list[OCRLine]:
    """Drop identical detections only when their boxes overlap on one page."""
    kept: list[OCRLine] = []
    for line in lines:
        duplicate = False
        for previous in kept:
            if line.text.strip() != previous.text.strip():
                continue
            overlap_width = max(
                0.0, min(line.bbox[2], previous.bbox[2]) - max(line.bbox[0], previous.bbox[0])
            )
            overlap_height = max(
                0.0, min(line.bbox[3], previous.bbox[3]) - max(line.bbox[1], previous.bbox[1])
            )
            area = max(0.0, line.bbox[2] - line.bbox[0]) * max(0.0, line.bbox[3] - line.bbox[1])
            previous_area = max(0.0, previous.bbox[2] - previous.bbox[0]) * max(
                0.0, previous.bbox[3] - previous.bbox[1]
            )
            if (
                area
                and previous_area
                and overlap_width * overlap_height / min(area, previous_area) >= 0.8
            ):
                duplicate = True
                break
        if not duplicate:
            kept.append(line)
    return kept


_ARTICLE_HEADING = re.compile(
    r"(?<!\S)(?:Điều|Dièu|Dieu|Ðiều)(?=\s+\d+[A-Za-z]?\s*[.:-]?(?:\s|$))", re.IGNORECASE
)
_ARTICLE_ONLY = re.compile(r"^(?:Điều|Dièu|Dieu|Ðiều)\s+\d+[A-Za-z]?\s*[.:-]$", re.IGNORECASE)
_TERMINAL_CUE = re.compile(
    r"(?:[.;:!?]$|\b(?:Điều|Dièu|Dieu|Ðiều|Khoản|Điểm|Mục|Chương|Phần)\s*$)", re.IGNORECASE
)


def _cuda_available() -> bool:
    try:
        import paddle

        return bool(paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0)
    except (ImportError, AttributeError, RuntimeError):
        return False


def resolve_ocr_device(requested: str | None = None) -> str:
    if requested:
        return requested
    if _cuda_available():
        return "gpu:0"
    print("OCR CUDA unavailable; using CPU (set OCR_DEVICE to override)", flush=True)
    return "cpu"


@dataclass(frozen=True)
class OCRLine:
    text: str
    bbox: tuple[float, float, float, float]
    detection_confidence: float | None
    recognition_confidence: float | None
    index: int
    merged_indices: tuple[int, ...] = ()


def _scalar(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


def _as_box(points: Any, width: int, height: int) -> tuple[float, float, float, float]:
    coords = [(_scalar(point[0]), _scalar(point[1])) for point in points]
    return (
        max(0.0, min(float(x) for x, _ in coords) / width),
        max(0.0, min(float(y) for _, y in coords) / height),
        min(1.0, max(float(x) for x, _ in coords) / width),
        min(1.0, max(float(y) for _, y in coords) / height),
    )


class _OCRResult(Protocol):
    def json(self) -> Any: ...


class _OCRPredictor(Protocol):
    def predict(self, image: Image.Image | str) -> Any: ...


def _predict(detector: Any, image_path: str | Path) -> _OCRResult:
    result = next(iter(detector.predict(str(image_path))))
    return cast(_OCRResult, result)


def _result_lines(result: _OCRResult, width: int, height: int) -> list[OCRLine]:
    data = getattr(result, "json", None)
    if callable(data):
        data = data()
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict):
        data = data.get("res", data)
    if not isinstance(data, dict):
        raise RuntimeError("unsupported PaddleOCR result shape")
    boxes = data.get("dt_polys") or data.get("polys") or []
    texts = data.get("rec_texts") or []
    scores = data.get("rec_scores") or []
    detections = data.get("det_scores") or []
    lines: list[OCRLine] = []
    for index, points in enumerate(boxes):
        text = str(_scalar(texts[index])) if index < len(texts) else ""
        if not text.strip():
            continue
        score = float(_scalar(scores[index])) if index < len(scores) else None
        det_score = float(_scalar(detections[index])) if index < len(detections) else None
        lines.append(OCRLine(text, _as_box(points, width, height), det_score, score, index))
    return sorted(lines, key=lambda line: (line.bbox[1], line.bbox[0]))


def _merge_ocr_lines(lines: list[OCRLine]) -> list[OCRLine]:
    merged: list[OCRLine] = []
    for line in lines:
        if not merged:
            merged.append(line)
            continue
        previous = merged[-1]
        gap = line.bbox[1] - previous.bbox[3]
        overlap = max(
            0.0, min(previous.bbox[2], line.bbox[2]) - max(previous.bbox[0], line.bbox[0])
        )
        span = min(previous.bbox[2] - previous.bbox[0], line.bbox[2] - line.bbox[0])
        adequate_overlap = span > 0 and overlap / span >= OCR_LINE_MERGE_MIN_OVERLAP
        article_heading = bool(_ARTICLE_ONLY.fullmatch(previous.text.strip()))
        can_merge = 0 <= gap <= OCR_LINE_MERGE_MAX_GAP and (
            article_heading
            or (adequate_overlap and not _TERMINAL_CUE.search(previous.text.strip()))
        )
        if not can_merge:
            merged.append(line)
            continue
        merged[-1] = OCRLine(
            text=f"{previous.text.strip()} {line.text.strip()}",
            bbox=(
                min(previous.bbox[0], line.bbox[0]),
                min(previous.bbox[1], line.bbox[1]),
                max(previous.bbox[2], line.bbox[2]),
                max(previous.bbox[3], line.bbox[3]),
            ),
            detection_confidence=min(
                (
                    v
                    for v in (previous.detection_confidence, line.detection_confidence)
                    if v is not None
                ),
                default=None,
            ),
            recognition_confidence=min(
                (
                    v
                    for v in (previous.recognition_confidence, line.recognition_confidence)
                    if v is not None
                ),
                default=None,
            ),
            index=previous.index,
            merged_indices=previous.merged_indices + (line.index,),
        )
    return merged


def _normalize_article_heading(text: str) -> str:
    """Canonicalize OCR article keywords only when followed by an article number."""
    return _ARTICLE_HEADING.sub("Điều", text)


def _split_article_heading(element: DocumentElement) -> list[DocumentElement]:
    match = _ARTICLE_HEADING.search(element.text)
    if match is None or match.start() == 0:
        element.text = _normalize_article_heading(element.text)
        return [element]
    prefix = element.text[: match.start()].strip()
    suffix = _normalize_article_heading(element.text[match.start() :].strip())
    if not prefix or not suffix:
        element.text = _normalize_article_heading(element.text)
        return [element]
    first = element.model_copy(update={"text": prefix})
    second = element.model_copy(
        update={
            "element_id": f"{element.element_id}-article",
            "text": suffix,
            "reading_order": element.reading_order + 1,
            "raw_reference": {**element.raw_reference, "split_from_element_id": element.element_id},
        }
    )
    return [first, second]


def _recognize(predictor: Any, image: Image.Image) -> tuple[str, float | None]:
    result = cast(_OCRPredictor, predictor).predict(image)
    if isinstance(result, str):
        return result, None
    if isinstance(result, tuple):
        return str(result[0]), float(result[1]) if len(result) > 1 else None
    text = getattr(result, "text", None) or getattr(result, "pred", None)
    confidence = getattr(result, "confidence", None) or getattr(result, "score", None)
    return str(text if text is not None else result), float(
        confidence
    ) if confidence is not None else None


def _merge_elements(elements: list[DocumentElement]) -> list[DocumentElement]:
    merged: list[DocumentElement] = []
    for element in elements:
        if not merged or element.bbox is None or merged[-1].bbox is None:
            merged.append(element)
            continue
        previous = merged[-1]
        a, b = previous.bbox, element.bbox
        assert a is not None and b is not None
        gap = b.top - a.bottom
        overlap = max(0.0, min(a.right, b.right) - max(a.left, b.left))
        span = min(a.right - a.left, b.right - b.left)
        article = bool(_ARTICLE_ONLY.fullmatch(previous.text.strip()))
        if not (
            0 <= gap <= OCR_LINE_MERGE_MAX_GAP
            and (
                article
                or (
                    span > 0
                    and overlap / span >= OCR_LINE_MERGE_MIN_OVERLAP
                    and not _TERMINAL_CUE.search(previous.text.strip())
                )
            )
        ):
            merged.append(element)
            continue
        ids = previous.raw_reference.get("merged_element_ids", [previous.element_id]) + [
            element.element_id
        ]
        refs = previous.raw_reference.get(
            "merged_line_indices", [previous.raw_reference.get("detector_index")]
        ) + [element.raw_reference.get("detector_index")]
        previous.text = f"{previous.text.strip()} {element.text.strip()}"
        previous.bbox = BoundingBox(
            left=min(a.left, b.left),
            top=min(a.top, b.top),
            right=max(a.right, b.right),
            bottom=max(a.bottom, b.bottom),
            page_width=a.page_width,
            page_height=a.page_height,
        )
        previous.parser_confidence = min(
            (v for v in (previous.parser_confidence, element.parser_confidence) if v is not None),
            default=None,
        )
        previous.raw_reference = {
            **previous.raw_reference,
            "merged_element_ids": ids,
            "merged_line_indices": refs,
        }
    return merged


class HybridOCRAdapter:
    """Run PaddleOCR detection and VietOCR recognition once per detected line."""

    def __init__(
        self,
        *,
        device: str | None = None,
        recognition_mode: str = "paddle",
        vietocr_config: str = "vgg_seq2seq",
    ) -> None:
        if recognition_mode not in {"paddle", "vietocr"}:
            raise ValueError("recognition_mode must be 'paddle' or 'vietocr'")
        self.device = resolve_ocr_device(device)
        self.recognition_mode = recognition_mode
        self.vietocr_config = vietocr_config
        self._detector: Any = None
        self._recognizer: Any = None

    def _load_detector(self) -> None:
        if self._detector is None:
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]

            self._detector = PaddleOCR(
                lang="vi",
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="PP-OCRv5_mobile_rec",
                device=self.device,
                enable_mkldnn=False,
                cpu_threads=1,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )

    def _load_recognizer(self) -> None:
        if self._recognizer is None:
            try:
                from vietocr.tool.config import Cfg  # type: ignore[import-not-found]
                from vietocr.tool.predictor import Predictor  # type: ignore[import-not-found]
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "VietOCR mode requires a separately installed optional package"
                ) from exc
            config_path = os.environ.get("VIETOCR_CONFIG")
            config = (
                Cfg.load_config_from_file(config_path)
                if config_path
                else Cfg.load_config_from_name(self.vietocr_config)
            )
            config["device"] = self.device
            config["weights"] = os.environ.get("VIETOCR_WEIGHTS", config["weights"])
            config["predictor"]["beamsearch"] = False
            self._recognizer = Predictor(config)

    def parse_page(
        self, image_path: str | Path, *, page_number: int, document_id: str
    ) -> ParsedPage:
        self._load_detector()
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
        width, height = image.size
        result = _predict(self._detector, image_path)
        lines = _deduplicate_ocr_lines(_result_lines(result, width, height))
        elements: list[DocumentElement] = []
        for reading_order, line in enumerate(lines):
            text = line.text
            confidence = line.recognition_confidence
            if (
                confidence is None or confidence < OCR_MIN_RECOGNITION_CONFIDENCE
            ) and self.recognition_mode == "vietocr":
                self._load_recognizer()
                left, top, right, bottom = (
                    int(line.bbox[0] * width),
                    int(line.bbox[1] * height),
                    max(int(line.bbox[2] * width), 1),
                    max(int(line.bbox[3] * height), 1),
                )
                text, confidence = _recognize(
                    self._recognizer, image.crop((left, top, right, bottom))
                )
            if confidence is not None and confidence < OCR_MIN_RECOGNITION_CONFIDENCE:
                continue
            elements.append(
                DocumentElement(
                    element_id=f"p{page_number}-e{reading_order}",
                    element_type="paragraph",
                    text=text.strip(),
                    page_number=page_number,
                    bbox=BoundingBox(
                        left=line.bbox[0],
                        top=line.bbox[1],
                        right=line.bbox[2],
                        bottom=line.bbox[3],
                        page_width=width,
                        page_height=height,
                    ),
                    reading_order=reading_order,
                    parent_element_id=None,
                    table_html=None,
                    source_parser=VIETOCR_PARSER_NAME
                    if self.recognition_mode == "vietocr"
                    else PARSER_NAME,
                    parser_version=VIETOCR_PARSER_VERSION
                    if self.recognition_mode == "vietocr"
                    else PARSER_VERSION,
                    parser_confidence=confidence,
                    raw_reference={
                        "ocr_engine": VIETOCR_PARSER_NAME
                        if self.recognition_mode == "vietocr"
                        else PARSER_NAME,
                        "detection_confidence": line.detection_confidence,
                        "recognition_confidence": confidence,
                        "detector_index": line.index,
                        "image_path": str(image_path),
                        "document_id": document_id,
                    },
                )
            )
        elements = [split for element in elements for split in _split_article_heading(element)]
        elements = _merge_elements(elements)
        return ParsedPage(
            page_number=page_number,
            width=width,
            height=height,
            text="\n".join(e.text for e in elements),
            elements=elements,
        )

    def parse_document(
        self,
        pages: list[tuple[int, str | Path]],
        *,
        document_id: str,
        parsed_document_id: str,
        source_object_key: str,
        checkpoint_path: str | Path | None = None,
    ) -> ParsedDocument:
        started = datetime.now(UTC)
        checkpoint = Path(checkpoint_path) if checkpoint_path else None
        state: dict[str, Any] = (
            json.loads(checkpoint.read_text(encoding="utf-8"))
            if checkpoint and checkpoint.exists()
            else {"document_id": document_id, "pages": {}}
        )
        parsed_pages: dict[str, Any] = state.get("pages", {})
        for page_number, image_path in pages:
            key = str(page_number)
            if parsed_pages.get(key, {}).get("status") == "done":
                continue
            page = self.parse_page(image_path, page_number=page_number, document_id=document_id)
            parsed_pages[key] = {
                "status": "done",
                "page": page.model_dump(mode="json"),
                "provenance": {
                    "parser": VIETOCR_PARSER_NAME
                    if self.recognition_mode == "vietocr"
                    else PARSER_NAME,
                    "parser_version": VIETOCR_PARSER_VERSION
                    if self.recognition_mode == "vietocr"
                    else PARSER_VERSION,
                    "source_object_key": source_object_key,
                    "completed_at": datetime.now(UTC).isoformat(),
                },
            }
            if checkpoint:
                _atomic_checkpoint(checkpoint, {"document_id": document_id, "pages": parsed_pages})
        pages_out = [
            ParsedPage.model_validate(parsed_pages[str(number)]["page"])
            for number, _ in pages
            if str(number) in parsed_pages
        ]
        return ParsedDocument(
            parsed_document_id=parsed_document_id,
            document_id=document_id,
            parser=VIETOCR_PARSER_NAME if self.recognition_mode == "vietocr" else PARSER_NAME,
            parser_version=VIETOCR_PARSER_VERSION
            if self.recognition_mode == "vietocr"
            else PARSER_VERSION,
            ir_schema_version=IR_SCHEMA_VERSION,
            source_object_key=source_object_key,
            pages=pages_out,
            parse_started_at=started,
            parse_completed_at=datetime.now(UTC),
            quality_report={
                "ocr_pages": len(pages_out),
                "ocr_complete": len(pages_out) == len(pages),
                "checkpoint_path": str(checkpoint) if checkpoint else None,
            },
        )


def _atomic_checkpoint(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
