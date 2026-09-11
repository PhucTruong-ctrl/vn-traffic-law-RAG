"""Build chunks from an explicitly authorized local Markdown source directory.

Network retrieval is intentionally not part of the default workflow. The optional
single-URL mode is a controlled diagnostic and never retries or bypasses HTTP 403.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.ingestion.markdown import load_manifest, load_markdown, write_jsonl  # noqa: E402


def _fetch_one(url: str, output: Path) -> int:
    request = Request(url, headers={"User-Agent": "VNLRAG-local-source-loader/1.0"})
    try:
        with urlopen(request, timeout=20) as response:  # no redirects/retry policy is added
            body = response.read()
    except HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError(
                "HTTP 403 received; refusing retries or access-control bypass"
            ) from exc
        raise RuntimeError(f"source fetch failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"source fetch failed: {exc.reason}") from exc
    temporary = output.with_suffix(output.suffix + ".download")
    temporary.write_bytes(body)
    try:
        return write_jsonl(load_markdown(temporary, source_url=url, source_type="network"), output)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load authorized local Markdown sources into deterministic JSONL chunks."
    )
    parser.add_argument(
        "--local-dir", type=Path, help="directory containing manifest-listed Markdown files"
    )
    parser.add_argument("--manifest", type=Path, default=_ROOT / "data/sources/manifest.json")
    parser.add_argument(
        "--fallback-pdf-dir",
        type=Path,
        help="optional PDF directory used for manifest files missing from local Markdown",
    )
    parser.add_argument(
        "--output", type=Path, default=_ROOT / "data/processed/markdown-chunks.jsonl"
    )
    args = parser.parse_args(argv)
    if not args.local_dir:
        parser.error("--local-dir is required; provide already-saved Markdown files")
    chunks = load_manifest(args.manifest, local_dir=args.local_dir)
    print(f"loaded {len(chunks)} Markdown chunks")
    return write_jsonl(chunks, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
