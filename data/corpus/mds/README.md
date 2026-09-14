# Manual copy workflow

Copy each approved page's text into matching `.md` file in this directory. Keep front matter unchanged; update `retrieved_at`.

Run after copying all files:

```bash
cd backend
uv run python scripts/fetch_sources.py \
  --manifest ../data/sources/manifest.json \
  --local-dir ../data/corpus/mds \
  --output ../data/processed/markdown-chunks.jsonl
```

The manifest expects exact filenames. `nd-100-2019` has two PDF parts; copy each part into its corresponding file or update manifest deliberately.
