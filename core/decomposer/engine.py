"""The copista reader (kobimusic/copisteria): one page image in, one MusicXML file out.

The page's MusicXML is kept with two extra attributes on every <note>, ``dx`` and ``ds``: where the note sits on
the page (x in pixels) and on which staff (the page's staves counted from the top). Text found on the page (chord
symbols) is attached to notes by them; ``clean`` takes them out again before the score is written.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# what the reader was built from (its commit, our patches): pages read by another build are read again
BUILD = os.environ.get("DECOMPOSER_BUILD", "dev")
REV = 2                 # raise when this file changes what is kept for a page


def clean(xml: str) -> str:
    """The MusicXML without the note positions."""
    return re.sub(r' d[xs]="[^"]*"', "", xml)


class Copista:
    def __init__(self, detector: str = "28m"):
        self.detector = detector
        self.tag = f"copista-{detector}-{BUILD}-r{REV}"
        self._model = None

    def read(self, png: Path, out: Path) -> Path:
        """The page's MusicXML, written under ``out``. A page already read is not read again."""
        xml = out / f"{png.stem}.musicxml"
        if xml.exists():
            return xml
        # imported here: torch takes seconds to load, and a fully cached score needs none of it
        from PIL import Image
        from copisteria import pipeline, read, view, write
        from copisteria.paths import EVIDENCE
        from copisteria.revise import read_revised
        os.environ["COPISTERIA_DETECTOR"] = self.detector
        if self._model is None:
            self._model = read.load_model(EVIDENCE, "cpu")
        # as pipeline.run_page, with the reading in hand: the writer is told to note where each note sits
        dets, cands, feats = pipeline.inputs(png, self._model)
        im = Image.open(png).convert("L")
        rd = read_revised(dets, im.width, im.height, self._model, device="cpu", image=im, cands=cands, feats=feats)
        syms, plain = rd.layout.syms, write._note

        def located(meas, e, *args, **kwargs):
            done = plain(meas, e, *args, **kwargs)
            if 0 <= e.si < len(syms) and syms[e.si].staff >= 0:
                meas[-1].set("dx", f"{e.x:.1f}")
                meas[-1].set("ds", str(syms[e.si].staff))
            return done

        write._note = located
        try:
            text = write.write(rd, image=im)
        finally:
            write._note = plain
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{png.stem}.html").write_text(view.page_html(rd, png, clean(text), png.stem))
        (out / f"{png.stem}.layout.json").write_text(json.dumps({
            "systems": len(rd.layout.systems),
            "staves": [{"y0": st.y0, "y1": st.y1, "x0": st.x0, "x1": st.x1, "sp": st.sp, "system": st.system}
                       for st in rd.layout.staves]}))
        xml.write_text(text)
        return xml

    @staticmethod
    def layout(xml: Path) -> dict:
        return json.loads(xml.with_suffix(".layout.json").read_text())

    @staticmethod
    def summary(xml: Path) -> dict:
        """What was read on the page: its systems, parts and bars."""
        layout, text = Copista.layout(xml), xml.read_text()
        parts = text.count("<part id=")
        return {"systems": layout["systems"], "staves": len(layout["staves"]), "parts": parts,
                "bars": text.count("<measure ") // parts if parts else 0}
