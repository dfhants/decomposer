"""Write the score out as a MuseScore file, and render it back to page images for checking."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .ingest import CACHE

MSCORE = Path("/Applications/MuseScore 4.app/Contents/MacOS/mscore")


def _mscore(src: Path, out: Path) -> bool:
    out.unlink(missing_ok=True)
    # -f: MuseScore refuses a MusicXML file that fails schema validation unless forced, as the app's "load anyway".
    # The exit code is no guide: MuseScore 4 can abort on shutdown after writing the file.
    subprocess.run([str(MSCORE), "-f", "-o", str(out), str(src)], capture_output=True)
    return out.exists()


def mscz(xml: Path) -> Path | None:
    """The MusicXML converted to .mscz beside it, or None when MuseScore is missing or cannot read it."""
    out = xml.with_suffix(".mscz")
    return out if MSCORE.exists() and _mscore(xml, out) else None


def render(score: Path, dpi: int = 80) -> list[Path]:
    """The score engraved by MuseScore, one PNG per page. The score starts a new page where the source did, so
    page N here is page N of the source."""
    if not MSCORE.exists():
        raise RuntimeError("MuseScore 4 is not installed, so the score cannot be rendered")
    out = CACHE / "renders" / hashlib.sha256(score.read_bytes()).hexdigest()[:16]
    if not list(out.glob("page-*.png")):
        out.mkdir(parents=True, exist_ok=True)
        pdf = out / "score.pdf"
        if not _mscore(score, pdf):
            raise RuntimeError(f"MuseScore could not read {score.name}")
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(out / "page")], check=True)
    return sorted(out.glob("page-*.png"))
