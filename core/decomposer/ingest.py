"""Turn the input files into one greyscale PNG per page, in a cache folder keyed by the files' contents.

PDF pages are extracted by copisteria itself (it pulls an embedded scan out byte for byte, and rasterises only
when it must). Images are copied in; an image holding a two-page spread is cut into its two pages.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

CACHE = Path.home() / "Library" / "Caches" / "decomposer"
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SPREAD = 1.15           # an image this much wider than tall is taken for two facing pages
GOOD_SPACE = 8.0        # staff space in pixels from which a page reads well (the reader works at 10.6)
POOR_SPACE = 5.5        # below this the detail is not there: notes, clefs and accidentals are misread
POOR_HEIGHT = 1100      # a page this short, with no staves found by the quick check, is taken for low resolution


@dataclass
class Page:
    path: str               # the PNG
    source: str             # the input file's name, with the page of a PDF or the half of a spread
    width: int
    height: int
    space: float            # staff space in pixels by the quick staff finder; 0 when it finds none

    @property
    def resolution(self) -> str:
        if self.space >= GOOD_SPACE:
            return "good"
        if self.space >= POOR_SPACE:
            return "fair"
        if self.space > 0 or self.height < POOR_HEIGHT:
            return "poor"
        return "no staves found"


def _natural(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def expand(inputs: list[Path]) -> list[Path]:
    """The files to read: a folder stands for the PDFs and images in it, in natural order ("page 2" before
    "page 10"). Files given one by one keep the order given."""
    files: list[Path] = []
    for p in inputs:
        if p.is_dir():
            files += sorted((f for f in p.iterdir() if f.suffix.lower() in IMAGES | {".pdf"}), key=_natural)
        else:
            files.append(p)
    return files


def workdir(files: list[Path], split: bool = True) -> Path:
    """The cache folder for these files: the same files in the same order always give the same folder."""
    h = hashlib.sha256(b"split" if split else b"whole")
    for p in files:
        h.update(p.read_bytes())
    d = CACHE / h.hexdigest()[:16]
    d.mkdir(parents=True, exist_ok=True)
    return d


def gutter(im) -> int:
    """The column between a spread's two pages: the middle of the widest run of the emptiest columns in the
    middle tenth of the image."""
    import numpy as np
    a = np.asarray(im, dtype=np.float32)
    w = a.shape[1]
    lo, hi = int(w * 0.45), int(w * 0.55)
    ink = (255 - a[:, lo:hi]).sum(axis=0)
    empty = ink <= ink.min() + 1e-6
    best, run = (0, 0), None
    for i, e in enumerate([*empty, False]):
        if e and run is None:
            run = i
        elif not e and run is not None:
            if i - run > best[1] - best[0]:
                best = (run, i)
            run = None
    return lo + (best[0] + best[1]) // 2


def _page(png: Path, source: str) -> Page:
    from PIL import Image
    from copisteria.vision.page.staves import find_staves
    with Image.open(png) as im:
        im = im.convert("L")
        space = float(find_staves(im).spacing or 0)
        if space > im.height / 50:      # on a tiny page the finder locks onto the gaps between staves instead
            space = 0.0
        return Page(str(png), source, im.width, im.height, space)


def pages(files: list[Path], work: Path, split: bool = True) -> list[Page]:
    """Every page of every file, in order, as PNGs in ``work``. Pages already there are kept."""
    done = work / "pages.json"
    if done.exists():
        return [Page(**p) for p in json.loads(done.read_text())]
    from PIL import Image
    out: list[Page] = []
    for src in files:
        ext = src.suffix.lower()
        if ext == ".pdf":
            from copisteria.vision.page.scan import from_pdf
            info = subprocess.run(["pdfinfo", str(src)], capture_output=True, text=True, check=True).stdout
            count = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
            out += [_page(from_pdf(src, n, work).path, f"{src.name} p.{n}") for n in range(1, count + 1)]
        elif ext in IMAGES:
            with Image.open(src) as im:
                im = im.convert("L")
                halves = [(im, src.name)]
                if split and im.width > im.height * SPREAD:
                    x = gutter(im)
                    halves = [(im.crop((0, 0, x, im.height)), f"{src.name} (left half)"),
                              (im.crop((x, 0, im.width, im.height)), f"{src.name} (right half)")]
                for half, source in halves:
                    png = work / f"page-{len(out) + 1:03d}.png"
                    half.save(png)
                    out.append(_page(png, source))
        else:
            raise ValueError(f"{src.name}: not a PDF or an image")
    done.write_text(json.dumps([asdict(p) for p in out]))
    return out


def contact_sheets(pages: list[Page], work: Path, per_sheet: int = 10) -> list[Path]:
    """Images showing the top of every page, in order, each labelled with its number and source: the printed page
    numbers and first bar numbers are there, so one look tells whether the pages are in order."""
    from PIL import Image, ImageDraw
    WIDTH, LABEL, SHARE = 760, 20, 0.17
    sheets = []
    for s in range(0, len(pages), per_sheet):
        strips = []
        for n, p in enumerate(pages[s:s + per_sheet], s + 1):
            with Image.open(p.path) as im:
                top = im.convert("L").crop((0, 0, im.width, int(im.height * SHARE)))
                top = top.resize((WIDTH, max(1, round(top.height * WIDTH / top.width))), Image.LANCZOS)
            strips.append((f"{n}: {p.source}", top))
        sheet = Image.new("L", (WIDTH, sum(LABEL + t.height for _, t in strips)), 255)
        draw, y = ImageDraw.Draw(sheet), 0
        for label, top in strips:
            draw.rectangle((0, y, WIDTH, y + LABEL), fill=0)
            draw.text((6, y + 4), label, fill=255)
            sheet.paste(top, (0, y + LABEL))
            y += LABEL + top.height
        path = work / f"contact-{len(sheets) + 1}.png"
        sheet.save(path)
        sheets.append(path)
    return sheets
