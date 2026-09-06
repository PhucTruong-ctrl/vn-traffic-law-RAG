from __future__ import annotations

import json
from types import SimpleNamespace

from PIL import Image

from app.ingestion.adapters.hybrid_ocr_adapter import HybridOCRAdapter, _result_lines


def test_paddle_result_is_sorted_and_normalized_without_dropping_scores() -> None:
    result = SimpleNamespace(
        json=lambda: {
            "res": {
                "dt_polys": [
                    [[80, 50], [180, 50], [180, 80], [80, 80]],
                    [[10, 10], [90, 10], [90, 30], [10, 30]],
                ],
                "rec_texts": ["bottom", "top"],
                "rec_scores": [0.91, 0.95],
                "det_scores": [0.87, 0.89],
            }
        }
    )
    lines = _result_lines(result, 200, 100)
    assert [line.text for line in lines] == ["top", "bottom"]
    assert lines[0].bbox == (0.05, 0.1, 0.45, 0.3)
    assert lines[1].detection_confidence == 0.87
    assert lines[0].recognition_confidence == 0.95


def test_parse_page_recognizes_each_detected_line_and_quarantines_low_confidence(
    tmp_path,
) -> None:
    image_path = tmp_path / "page.jpg"
    Image.new("RGB", (100, 100), "white").save(image_path)
    adapter = HybridOCRAdapter(recognition_mode="vietocr")
    adapter._detector = SimpleNamespace(
        predict=lambda _: iter(
            [
                SimpleNamespace(
                    json=lambda: {
                        "res": {
                            "dt_polys": [
                                [[0, 0], [50, 0], [50, 20], [0, 20]],
                                [[0, 30], [50, 30], [50, 50], [0, 50]],
                            ],
                            "rec_texts": ["detected", "ignored"],
                            "rec_scores": [0.95, 0.40],
                            "det_scores": [0.90, 0.90],
                        }
                    }
                )
            ]
        )
    )
    calls = []
    adapter._recognizer = SimpleNamespace(
        predict=lambda crop: (
            calls.append(crop.size) or ("recognized", 0.90 if len(calls) == 1 else 0.40)
        )
    )
    page = adapter.parse_page(image_path, page_number=1, document_id="doc")
    assert [element.text for element in page.elements] == ["detected", "recognized"]
    assert calls == [(50, 20)]


def test_parse_document_writes_atomic_page_checkpoint_and_resumes(tmp_path) -> None:
    image_path = tmp_path / "page.jpg"
    Image.new("RGB", (10, 10), "white").save(image_path)
    checkpoint = tmp_path / "checkpoint.json"
    adapter = HybridOCRAdapter()
    adapter._detector = SimpleNamespace(
        predict=lambda _: iter(
            [
                SimpleNamespace(
                    json=lambda: {
                        "res": {
                            "dt_polys": [[[0, 0], [10, 0], [10, 10], [0, 10]]],
                            "rec_texts": ["line"],
                            "rec_scores": [0.95],
                            "det_scores": [0.95],
                        }
                    }
                )
            ]
        )
    )
    adapter._recognizer = SimpleNamespace(predict=lambda _: ("line", 0.95))
    parsed = adapter.parse_document(
        [(1, image_path)],
        document_id="doc",
        parsed_document_id="parse",
        source_object_key="source.pdf",
        checkpoint_path=checkpoint,
    )
    saved = json.loads(checkpoint.read_text())
    assert saved["pages"]["1"]["status"] == "done"
    assert parsed.quality_report["ocr_complete"] is True
    adapter._detector = SimpleNamespace(
        predict=lambda _: (_ for _ in ()).throw(AssertionError("page should be resumed"))
    )
    resumed = adapter.parse_document(
        [(1, image_path)],
        document_id="doc",
        parsed_document_id="parse",
        source_object_key="source.pdf",
        checkpoint_path=checkpoint,
    )
    assert resumed.pages[0].text == "line"
