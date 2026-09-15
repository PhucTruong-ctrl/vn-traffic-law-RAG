"""Render the thesis diagram HTML sources to tightly cropped PNGs.

Usage (Playwright installed temporarily, not added to the project dependencies):

    uv run --with playwright python scripts/render_diagrams.py ch2_rrf ch3_cdm   # render selected sources
    uv run --with playwright python scripts/render_diagrams.py --all-trim        # trim every existing PNG in place

Rendering happens at 1760x1100 CSS pixels with a device scale factor of 2 and the
result is cropped to the drawn content plus a small margin, so a small LaTeX
figure width stays readable on paper.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "docs" / "diagrams" / "html"
TARGET_DIR = ROOT / "docs" / "diagrams"
FRAME = {"width": 1760, "height": 1100}
SCALE = 2
MARGIN = 32
TOLERANCE = 6


def _background(image: Image.Image) -> tuple[int, int, int]:
    """Most common colour along the image border, i.e. the page paper."""
    width, height = image.size
    pixels = (
        [image.getpixel((x, 0)) for x in range(0, width, 8)]
        + [image.getpixel((x, height - 1)) for x in range(0, width, 8)]
        + [image.getpixel((0, y)) for y in range(0, height, 8)]
        + [image.getpixel((width - 1, y)) for y in range(0, height, 8)]
    )
    return max(set(pixels), key=pixels.count)  # type: ignore[return-value]


def trim(path: Path, margin: int = MARGIN) -> tuple[int, int]:
    """Crop uniform paper borders, keeping ``margin`` pixels of breathing room."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        paper = Image.new("RGB", image.size, _background(image))
        box = ImageChops.difference(image, paper).convert("L").point(lambda v: 255 if v > TOLERANCE else 0).getbbox()
        if box is None:
            return image.size
        left = max(0, box[0] - margin)
        top = max(0, box[1] - margin)
        right = min(image.width, box[2] + margin)
        bottom = min(image.height, box[3] + margin)
        cropped = image.crop((left, top, right, bottom))
        cropped.save(path)
        return cropped.size


def _is_blank(image: Image.Image, paper: Image.Image, box: tuple[int, int, int, int]) -> bool:
    """True when the region holds nothing but page paper."""
    difference = ImageChops.difference(image.crop(box), paper.crop(box)).convert("L")
    return difference.point(lambda value: 255 if value > TOLERANCE else 0).getbbox() is None


def _blank_runs(image: Image.Image, paper: Image.Image, axis: str, gap: int, collapse_over: int) -> list[tuple[int, int]]:
    """Ranges of blank rows (axis "y") or columns (axis "x") taller than the limit."""
    length = image.height if axis == "y" else image.width
    runs: list[tuple[int, int]] = []
    start = None
    for index in range(length):
        box = (0, index, image.width, index + 1) if axis == "y" else (index, 0, index + 1, image.height)
        blank = _is_blank(image, paper, box)
        if blank and start is None:
            start = index
        elif not blank and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, length))
    return [(top, bottom) for top, bottom in runs if bottom - top > collapse_over]


def _collapse(image: Image.Image, axis: str, runs: list[tuple[int, int]], gap: int) -> Image.Image:
    """Rebuild the image, keeping only ``gap`` pixels of each blank run."""
    length = image.height if axis == "y" else image.width
    keep: list[tuple[int, int]] = []
    cursor = 0
    for top, bottom in runs:
        if top > cursor:
            keep.append((cursor, top))
        keep.append((top, min(bottom, top + gap)))
        cursor = bottom
    if cursor < length:
        keep.append((cursor, length))
    keep = [(start, end) for start, end in keep if end > start]
    new_length = sum(end - start for start, end in keep)
    size = (image.width, new_length) if axis == "y" else (new_length, image.height)
    rebuilt = Image.new("RGB", size, _background(image))
    position = 0
    for start, end in keep:
        chunk = image.crop((0, start, image.width, end)) if axis == "y" else image.crop((start, 0, end, image.height))
        rebuilt.paste(chunk, (0, position) if axis == "y" else (position, 0))
        position += end - start
    return rebuilt


def tighten(path: Path, gap: int = 40, collapse_over: int = 72) -> tuple[int, int]:
    """Drop the empty bands a page layout leaves above, below and beside the drawing.

    Runs of blank rows or columns longer than ``collapse_over`` shrink to ``gap``,
    so the exported file holds the drawn nodes rather than the page skeleton.
    """
    with Image.open(path) as source:
        image = source.convert("RGB")
        paper = Image.new("RGB", image.size, _background(image))
        image = _collapse(image, "y", _blank_runs(image, paper, "y", gap, collapse_over), gap)
        image = _collapse(image, "x", _blank_runs(image, paper, "x", gap, collapse_over), gap)
        image.save(path)
        return image.size


def render(names: list[str]) -> int:
    rendered = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=FRAME, device_scale_factor=SCALE)
        for name in names:
            source = SOURCE_DIR / f"{name}.html"
            if not source.exists():
                print(f"missing source: {source}")
                continue
            page.goto(source.as_uri(), wait_until="networkidle")
            page.wait_for_timeout(300)
            target = TARGET_DIR / f"{name}.png"
            page.screenshot(path=str(target))
            size = tighten(target)
            print(f"{target.relative_to(ROOT)}  {size[0]}x{size[1]}")
            rendered += 1
        browser.close()
    return rendered


def trim_all() -> int:
    trimmed = 0
    for target in sorted(TARGET_DIR.glob("*.png")):
        size = trim(target)
        print(f"{target.relative_to(ROOT)}  {size[0]}x{size[1]}")
        trimmed += 1
    return trimmed


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if arguments == ["--all-trim"]:
        count = trim_all()
    else:
        count = render(arguments)
    print(f"processed {count} diagram(s)")
    raise SystemExit(0 if count else 1)
