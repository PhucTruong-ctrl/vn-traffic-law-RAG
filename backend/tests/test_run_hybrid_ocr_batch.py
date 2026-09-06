from __future__ import annotations

import ast
from pathlib import Path


def test_hybrid_ocr_batch_uses_task_result_output_directory() -> None:
    source = Path(__file__).parents[1] / "scripts" / "run_hybrid_ocr_batch.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    defaults = {
        node.targets[0].id: node.value.args[0].value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "Path"
        and node.value.args
        and isinstance(node.value.args[0], ast.Constant)
    }
    assert defaults["DEFAULT_OUTPUT"] == "/tmp/vnlrag-task1-ocr-result"
