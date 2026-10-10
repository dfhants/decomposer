"""decomposer: sheet music PDFs and scans to one MusicXML score.

  decomposer inspect <files or a folder>     the pages as they will be read, before reading them
  decomposer convert <files or a folder>     read the pages and write the score
  decomposer render <score>                  the written score as page images, to check it against the source
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import export, ingest
from .engine import Copista
from .stitch import stitch

app = typer.Typer(add_completion=False, no_args_is_help=True, pretty_exceptions_enable=False)

Inputs = Annotated[list[Path], typer.Argument(exists=True, help="PDFs, images, or a folder of them, in page order")]
Split = Annotated[bool, typer.Option(help="Cut an image of two facing pages into its two pages")]


def say(text: str = "") -> None:
    print(text, flush=True)


def _pages(inputs: list[Path], split: bool):
    files = ingest.expand(inputs)
    if not files:
        raise typer.BadParameter("no PDFs or images found")
    work = ingest.workdir(files, split)
    return files, work, ingest.pages(files, work, split)


def _table(pages: list[ingest.Page]) -> None:
    wide = max(len(p.source) for p in pages)
    say(f"  #  {'source'.ljust(wide)}  size         staff space  resolution")
    for n, p in enumerate(pages, 1):
        space = f"{p.space:.1f} px" if p.space else "-"
        say(f"{n:3d}  {p.source.ljust(wide)}  {f'{p.width}x{p.height}'.ljust(11)}  {space.ljust(11)}  {p.resolution}")


def _resolution_warnings(pages: list[ingest.Page]) -> list[str]:
    out = []
    poor = [str(n) for n, p in enumerate(pages, 1) if p.resolution == "poor"]
    none = [str(n) for n, p in enumerate(pages, 1) if p.resolution == "no staves found"]
    if poor:
        out.append(f"low resolution on page {', '.join(poor)}: the staves are too small to read well, so expect "
                   f"wrong notes, clefs and accidentals. A larger scan or the original PDF reads far better.")
    if none:
        out.append(f"no staves found by the quick check on page {', '.join(none)}: a title page, a blank page, "
                   f"or not sheet music. It is still read; leave the file out if it is not music.")
    return out


@app.command()
def inspect(inputs: Inputs, split: Split = True) -> None:
    """The pages as they will be read: their order, size and resolution, and a contact sheet of their tops."""
    files, work, pages = _pages(inputs, split)
    say(f"{len(pages)} pages from {len(files)} files")
    _table(pages)
    for w in _resolution_warnings(pages):
        say(f"warning: {w}")
    for sheet in ingest.contact_sheets(pages, work):
        say(f"contact sheet: {sheet}")
    say("The contact sheet shows the top of every page in this order. Read it and check that the printed page "
        "numbers and bar numbers run upwards; if they do not, pass the files to convert one by one in the right order.")


@app.command()
def convert(
    inputs: Inputs,
    out: Annotated[Optional[Path], typer.Option(help="Folder for the result (default: beside the first input)")] = None,
    name: Annotated[Optional[str], typer.Option(help="File name of the result, without extension")] = None,
    title: Annotated[Optional[str], typer.Option(help="The piece's title, written into the score")] = None,
    composer: Annotated[Optional[str], typer.Option(help="The composer, written into the score")] = None,
    parts: Annotated[Optional[str], typer.Option(help='Part names from the top staff down, e.g. "Soprano/Alto,Tenor/Bass,Piano"')] = None,
    detector: Annotated[str, typer.Option(help="28m (more accurate) or 2m (faster)")] = "28m",
    split: Split = True,
) -> None:
    """Read the pages and write one score: MusicXML, and a MuseScore file when MuseScore is installed."""
    files, work, pages = _pages(inputs, split)
    first = inputs[0]
    out = out or (first if first.is_dir() else first.parent)
    name = name or title or first.stem
    engine = Copista(detector)
    reads = work / engine.tag
    read, warnings = [], _resolution_warnings(pages)
    wide = max(len(p.source) for p in pages)
    for n, page in enumerate(pages, 1):
        xml = engine.read(Path(page.path), reads)
        s = engine.summary(xml)
        read.append((page, xml, s))
        say(f"page {n}/{len(pages)}  {page.source.ljust(wide)}  {s['systems']} systems  {s['bars']} bars  {s['parts']} parts")

    counts = [s["parts"] for _, _, s in read if s["parts"]]
    usual = max(set(counts), key=counts.count) if counts else 0
    empty = [str(n) for n, (_, _, s) in enumerate(read, 1) if not s["bars"]]
    odd = [f"{n} ({s['parts']})" for n, (_, _, s) in enumerate(read, 1) if s["parts"] and s["parts"] != usual]
    if empty:
        warnings.append(f"no music read on page {', '.join(empty)}")
    if odd:
        warnings.append(f"most pages read as {usual} parts, but page {', '.join(odd)} differs. The parts were "
                        f"matched from the bottom staff up and the missing ones given rests; check those pages.")
    names = [p.strip() for p in parts.split(",")] if parts else None
    total = max(counts, default=0)
    if names and len(names) != total:
        warnings.append(f"--parts names {len(names)} parts but the score has {total}; names were given from the top "
                        f"down as far as they go")

    out.mkdir(parents=True, exist_ok=True)
    score = out / f"{name}.musicxml"
    text = stitch([xml.read_text() for _, xml, _ in read if xml.read_text().count("<part id=")],
                  title=title, composer=composer, part_names=names)
    score.write_text(text)
    mscz = export.mscz(score)
    viewer = reads / "index.html"
    shutil.copy(Path(__file__).with_name("viewer.html"), viewer)
    (reads / "pages.js").write_text("const PAGES = " + json.dumps([xml.with_suffix(".html").name for _, xml, _ in read]))

    say()
    say(f"score: {score}  ({text.count('<measure ') // max(1, total)} bars, {total} parts)")
    say(f"musescore: {mscz}" if mscz else "musescore: not written (MuseScore 4 is not installed, or it could not read the score)")
    say(f"viewer: {viewer}")
    say(f"page images: {Path(pages[0].path).parent}/  ({Path(pages[0].path).name} ...)")
    for w in warnings:
        say(f"warning: {w}")
    say("Lyrics are not read. To check the result, run: decomposer render \"" + str(score) + "\"")


@app.command()
def render(score: Annotated[Path, typer.Argument(exists=True, help="A .musicxml or .mscz file")]) -> None:
    """The score engraved as page images, to compare with the source pages."""
    try:
        images = export.render(score)
    except RuntimeError as e:
        say(f"error: {e}")
        raise typer.Exit(1)
    say(f"{len(images)} pages. A score written by convert starts a new page where the source did, so page N here "
        f"is page N of the source.")
    for image in images:
        say(str(image))


if __name__ == "__main__":
    app(prog_name="decomposer")
