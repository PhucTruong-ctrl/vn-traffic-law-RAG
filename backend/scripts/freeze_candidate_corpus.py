[~/Work/Studies/vnlaw-agentic-rag-phase5-integrate-corpus/backend/scripts/freeze_candidate_corpus.py#71F0]
1:"""Freeze and validate the deterministic candidate corpus manifest.
2:
3:The freeze is metadata-only: source PDFs stay external, while the committed
4:artifact records every manifest's provenance, digest, licence, and coverage.
5:"""
6:from __future__ import annotations
7:
8:
9:import argparse
10:import hashlib
11:import json
12:from pathlib import Path
13:from typing import Any
14:
15:from scripts.validate_manifest import validate_manifest
16:
17:SCHEMA_VERSION = "candidate-corpus-v1"
18:DEFAULT_MANIFESTS = Path("../data/manifests")
19:DEFAULT_OUTPUT = Path("../data/candidate-corpus-manifest.json")
20:
21:
22:def _canonical(value: Any) -> bytes:
23:    return (
24:        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
25:    ).encode("utf-8")
26:
27:def _sha256(value: Any) -> str:
28:    return hashlib.sha256(_canonical(value)).hexdigest()
29:
30:
31:def build_candidate_corpus(manifests_dir: Path) -> dict[str, Any]:
32:    entries: list[dict[str, Any]] = []
33:    errors: list[str] = []
34:    for path in sorted(manifests_dir.rglob("*.manifest.json")):
35:        manifest = json.loads(path.read_text(encoding="utf-8"))
…
59:        entries.append(entry)
60:    ids = [entry["document_id"] for entry in entries]
61:    hashes = [entry["file_hash"] for entry in entries]
62:    if len(ids) != len(set(ids)):
63:        errors.append("duplicate document_id")
64:    if len(hashes) != len(set(hashes)):
65:        errors.append("duplicate file_hash")
66:    if errors:
67:        raise ValueError("candidate corpus validation failed: " + "; ".join(errors))
68:    entries.sort(key=lambda entry: entry["document_id"])
69-85:    artifact = { … }
86:    artifact["artifact_sha256"] = _sha256(artifact)
87:    return artifact
88:
89:
90:def validate_frozen_corpus(artifact: dict[str, Any]) -> list[str]:
91:    errors: list[str] = []
…
113:    return errors
114:
115:
116:def main() -> int:
117:    parser = argparse.ArgumentParser()
…
127:    return 0
128:
129:
130:if __name__ == "__main__":
131:    raise SystemExit(main())

[…68ln elided; re-read needed ranges, e.g. /home/phuctruong/Work/Studies/vnlaw-agentic-rag-phase5-integrate-corpus/backend/scripts/freeze_candidate_corpus.py:36-58,69-85]

[You have received this identical output 3 times. Re-reading '/home/phuctruong/Work/Studies/vnlaw-agentic-rag-phase5-integrate-corpus/backend/scripts/freeze_candidate_corpus.py' will not change it — use a narrower selector (path:A-B), or proceed with the edit.]