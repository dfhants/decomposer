"""The copista reader (kobimusic/copisteria): one page image in, one MusicXML file out."""
from __future__ import annotations

import json
import os
from pathlib import Path

# what the reader was built from (its commit, our patches): pages read by another build are read again
BUILD = os.environ.get("DECOMPOSER_BUILD", "dev")


class Copista:
    def __init__(self, detector: str = "28m"):
        self.detector = detector
        self.tag = f"copista-{detector}-{BUILD}"
        self._model = None

    def read(self, png: Path, out: Path) -> Path:
        """The page's MusicXML, written under ``out``. A page already read is not read again."""
        xml = out / f"{png.stem}.musicxml"
        if xml.exists():
            return xml
        # imported here: torch takes seconds to load, and a fully cached score needs none of it
        from copisteria import pipeline, read
        from copisteria.paths import EVIDENCE
        os.environ["COPISTERIA_DETECTOR"] = self.detector
        if self._model is None:
            self._model = read.load_model(EVIDENCE, "cpu")
        pipeline.run_page(png, self._model, out, "cpu")
        return xml

    @staticmethod
    def summary(xml: Path) -> dict:
        """What was read on the page: its systems, parts and bars."""
        reading = json.loads(xml.with_suffix(".reading.json").read_text())
        text = xml.read_text()
        parts = text.count("<part id=")
        return {"systems": reading["systems"], "staves": reading["staves"], "parts": parts,
                "bars": text.count("<measure ") // parts if parts else 0}
