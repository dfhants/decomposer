"""Chord symbols: the letters printed above a staff ("Dm7", "G/B") become <harmony> elements on the notes below.

The reader does not see them, so each page's bands above its staves are read as text. A band is taken for a line
of chord symbols only when most of its words are chord symbols: the band above a choir's second staff holds the
first staff's lyrics, where "A" and "Am" are words.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

ABOVE = 8.0             # a band reaches this many staff spaces above its staff
CLEAR = 0.4             # ... and stops this far above the top line
READ_SPACE = 16.0       # bands are enlarged until a staff space is at least this many pixels
MOSTLY = 0.6            # share of a band's words that must be chord symbols
LONE_PAGE = 4           # a page with fewer symbols than this keeps only staves that have two or more
ON_NOTE = 1.5           # a symbol within this many staff spaces of a note stands on it

# what a recogniser makes of the symbols' glyphs
GLYPHS = str.maketrans({"♯": "#", "♭": "b", "△": "Δ", "º": "°", "˚": "°", "Ø": "ø",
                        "А": "A", "В": "B", "С": "C", "Е": "E", "М": "M", "О": "O"})
ROOT = r"([A-G])([#b]?)"
SYMBOL = re.compile(rf"^{ROOT}([^/]*)(?:/{ROOT})?$")
QUALITY = re.compile(r"^(maj|min|dim|aug|sus|add|omit|no|M|m|°|ø|Δ|\+|-|#|b|[0-9]|\(|\)|,)*$")
KINDS = {
    "": "major", "M": "major", "maj": "major", "m": "minor", "min": "minor", "-": "minor",
    "7": "dominant", "maj7": "major-seventh", "M7": "major-seventh", "Δ": "major-seventh", "Δ7": "major-seventh",
    "m7": "minor-seventh", "min7": "minor-seventh", "-7": "minor-seventh",
    "dim": "diminished", "°": "diminished", "dim7": "diminished-seventh", "°7": "diminished-seventh",
    "aug": "augmented", "+": "augmented", "m7b5": "half-diminished", "ø": "half-diminished", "ø7": "half-diminished",
    "mmaj7": "major-minor", "mM7": "major-minor", "6": "major-sixth", "m6": "minor-sixth",
    "9": "dominant-ninth", "maj9": "major-ninth", "M9": "major-ninth", "m9": "minor-ninth",
    "11": "dominant-11th", "m11": "minor-11th", "13": "dominant-13th", "maj13": "major-13th", "m13": "minor-13th",
    "sus": "suspended-fourth", "sus4": "suspended-fourth", "sus2": "suspended-second", "5": "power",
}
# a kind with notes added or altered: (kind, [(degree, alter, add|alter)])
DEGREES = {
    "add9": ("major", [(9, 0, "add")]), "add2": ("major", [(9, 0, "add")]), "2": ("major", [(9, 0, "add")]),
    "madd9": ("minor", [(9, 0, "add")]), "7sus4": ("suspended-fourth", [(7, -1, "add")]),
    "7sus": ("suspended-fourth", [(7, -1, "add")]), "7b9": ("dominant", [(9, -1, "add")]),
    "7#9": ("dominant", [(9, 1, "add")]), "7b5": ("dominant", [(5, -1, "alter")]),
    "7#5": ("dominant", [(5, 1, "alter")]), "maj7#11": ("major-seventh", [(11, 1, "add")]),
    "69": ("major-sixth", [(9, 0, "add")]), "6/9": ("major-sixth", [(9, 0, "add")]),
}


@dataclass
class Chord:
    text: str               # as normalised, e.g. "Bm7b5"
    x: float                # its left edge on the page
    x1: float               # ... and its right edge
    staff: int              # the staff it stands over, counted from the top of the page
    root: str
    root_alter: int
    quality: str            # what follows the root: "m7b5"
    bass: str = ""
    bass_alter: int = 0


def parse(word: str) -> dict | None:
    """The chord a word names, or None when it is not a chord symbol."""
    w = word.translate(GLYPHS).strip(".,;:")
    # a flat sign before an altered fifth or ninth is read as a 6: "Bm765" is Bm7b5
    w = re.sub(r"(?<=7)6(?=[59](\b|/|$))", "b", w)
    m = SYMBOL.match(w)
    if not m or len(w) > 12:
        return None
    root, acc, quality, bass, bass_acc = m.groups()
    quality = quality.replace("(", "").replace(")", "")
    # small capitals and superscripts come back in any case ("F(suS2)"), and a superscript 5 as an S ("CS")
    quality = re.sub(r"(?i)sus|add|maj|min|dim|aug|omit|no(?=\d)", lambda w: w.group().lower(), quality)
    if quality == "S":
        quality = "5"
    if not QUALITY.match(quality):
        return None
    alter = {"#": 1, "b": -1, "": 0}
    w = root + acc + quality + (f"/{bass}{bass_acc}" if bass else "")
    return {"text": w, "root": root, "root_alter": alter[acc], "quality": quality,
            "bass": bass or "", "bass_alter": alter[bass_acc or ""]}


GLYPH_GAP = 0.25        # ink closer than this many staff spaces belongs to one glyph or to touching glyphs


def _runs(band, sp: float) -> list[tuple[int, int]]:
    """Where the ink of a band lies from left to right: (start, end) of each stretch of glyphs."""
    import numpy as np
    runs: list[list[int]] = []
    for x in np.flatnonzero(_ink(band).any(axis=0)):
        if runs and x - runs[-1][1] <= GLYPH_GAP * sp:
            runs[-1][1] = int(x)
        else:
            runs.append([int(x), int(x)])
    return [(a, b + 1) for a, b in runs]


def _ink(band):
    import numpy as np
    a = np.asarray(band)
    return a < (int(a.min()) + int(np.median(a))) / 2


def _read(image, sp: float, runs: list[tuple[int, int]]) -> list[tuple[float, float, float, str]]:
    """Every word in an image, read at two sizes (a lone letter missed at one is often found at the other):
    (left, right, height of its middle, word)."""
    from PIL import Image

    from . import ocr

    def edge(x: float, side: int) -> float:
        """The recogniser's word boxes are rough: an edge is moved to the nearest edge of ink, if one is near."""
        near = min((r[side] for r in runs), key=lambda e: abs(e - x), default=x)
        return near if abs(near - x) <= 1.5 * sp else x

    base = max(1, round(READ_SPACE / sp + 0.49))
    out = []
    for scale in (base, 2 * base):
        big = image if scale == 1 else image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
        out += [(edge(b[0] / scale, 0), edge(b[2] / scale, 1), (b[1] + b[3]) / 2 / scale, w)
                for w, b in ocr.words(big)]
    return out


def _places(words: list, sp: float) -> list[list]:
    """One place on a line, however many times it was read: [left, right, [readings]], from left to right."""
    places: list[list] = []
    for x0, x1, _, w in sorted(words, key=lambda w: w[0]):
        if places and x0 - places[-1][0] < 0.5 * sp:
            places[-1][2].append(w)
            places[-1][1] = max(places[-1][1], x1)
        else:
            places.append([x0, x1, [w]])
    return places


def _is_chord_line(places: list[list]) -> bool:
    # bar numbers and punctuation say nothing about what a line is
    said = [p for p in places if any(re.search(r"[A-Za-z]", w) for w in p[2])]
    return bool(said) and sum(any(parse(w) for w in p[2]) for p in said) >= MOSTLY * len(said)


def _lone(strip, sp: float, covered: list[list], anchor) -> list[tuple[float, float, float, str]]:
    """Symbols the recogniser passed over: a letter standing alone is often missed in a line, and read when it
    is set between two symbols it did read. Each stretch of ink no word covers is read between two copies of
    ``anchor``, a symbol from the same line."""
    from PIL import Image
    groups: list[list[int]] = []
    for a, b in _runs(strip, sp):
        if groups and a - groups[-1][1] <= 0.6 * sp:
            groups[-1][1] = b
        else:
            groups.append([a, b])
    ink = _ink(strip)
    out = []
    for a, b in groups:
        if any(x0 - 0.3 * sp <= (a + b) / 2 <= x1 + 0.3 * sp for x0, x1, _ in covered):
            continue
        rows = ink[:, a:b].any(axis=1)
        if not 0.3 * sp <= b - a <= 8 * sp or rows.sum() < 0.8 * sp:       # a stem, a slur, a bracket's line
            continue
        pad = int(1.5 * sp)
        piece = strip.crop((max(0, a - pad // 3), 0, min(strip.width, b + pad // 3), strip.height))
        line = Image.new("L", (2 * anchor.width + piece.width + 4 * pad, strip.height), 255)
        line.paste(anchor, (pad, 0))
        line.paste(piece, (anchor.width + 2 * pad, 0))
        line.paste(anchor, (anchor.width + piece.width + 3 * pad, 0))
        lo, hi = anchor.width + 1.5 * pad, anchor.width + piece.width + 2.5 * pad
        for x0, x1, y, w in _read(line, sp, []):
            if lo <= (x0 + x1) / 2 <= hi and parse(w):
                out.append((float(a), float(b), y, w))
                break
    return out


def _read_band(band, sp: float) -> list[tuple[float, float, dict]]:
    """The chord symbols in the band above a staff: (left edge, right edge, chord) from left to right.

    The band holds more than chord symbols: the lyrics of the system above, a rehearsal box, a volta bracket,
    stems and notes rising out of the staff. So its words are sorted into lines of text, the line nearest the
    staff that is mostly chord symbols is taken, and the strip it stands in is read again on its own."""
    words = _read(band, sp, _runs(band, sp))
    lines: list[list] = []
    for w in sorted(words, key=lambda w: w[2]):
        if lines and w[2] - lines[-1][-1][2] < 0.8 * sp:
            lines[-1].append(w)
        else:
            lines.append([w])
    line = next((ln for ln in reversed(lines) if _is_chord_line(_places(ln, sp))), None)
    if line is None:
        return []
    mid = sorted(w[2] for w in line)[len(line) // 2]
    lo, hi = max(0, int(mid - 1.4 * sp)), min(band.height, int(mid + 1.4 * sp))
    strip = band.crop((0, lo, band.width, hi))
    again = _read(strip, sp, _runs(strip, sp))
    places = _places(again if len(_places(again, sp)) >= len(_places(line, sp)) else line, sp)
    read = [p for p in places if any(parse(w) for w in p[2])]
    if read:
        widest = max(read, key=lambda p: p[1] - p[0])
        anchor = strip.crop((max(0, int(widest[0] - 0.3 * sp)), 0, min(strip.width, int(widest[1] + 0.3 * sp)),
                             strip.height))
        places = _places([(p[0], p[1], 0.0, w) for p in places for w in p[2]] + _lone(strip, sp, places, anchor), sp)
    out: list[tuple[float, float, dict]] = []
    for x0, x1, ws in places:
        # a place read as a number at either size is a bar number
        c = None if any(re.fullmatch(r"\d+", w) for w in ws) else next((c for c in map(parse, ws) if c), None)
        # one symbol whose edges were found differently at the two sizes
        if c and not (out and out[-1][2]["text"] == c["text"] and x0 - out[-1][0] < 2 * sp):
            out.append((x0, x1, c))
    return out


def find(png: Path, layout: dict) -> list[Chord]:
    """The chord symbols printed on the page, each with the staff it stands over."""
    from PIL import Image
    staves = layout["staves"]
    out: list[Chord] = []
    with Image.open(png) as im:
        im = im.convert("L")
        for k, st in enumerate(staves):
            sp = st["sp"]
            top = st["y0"] - ABOVE * sp
            if k and staves[k - 1]["y1"] > top:         # not into the staff above
                top = staves[k - 1]["y1"] + CLEAR * sp
            box = (0, max(0, round(top)), im.width, round(st["y0"] - CLEAR * sp))
            if box[3] - box[1] < 1.5 * sp:
                continue
            # over the staff, not beside it: a part's abbreviated name ("A." for the altos) stands left of it
            out += [Chord(x=x0, x1=x1, staff=k, **c) for x0, x1, c in _read_band(im.crop(box), sp)
                    if x0 >= st["x0"] - sp]
    # one letter alone over a staff is a rehearsal mark, unless the page has chord symbols elsewhere
    if len(out) < LONE_PAGE:
        out = [c for c in out if sum(o.staff == c.staff for o in out) >= 2]
    return out


def _harmony(c: Chord, staff_no: str | None, offset: int) -> ET.Element:
    h = ET.Element("harmony")
    root = ET.SubElement(h, "root")
    ET.SubElement(root, "root-step").text = c.root
    if c.root_alter:
        ET.SubElement(root, "root-alter").text = str(c.root_alter)
    kind, degrees = DEGREES.get(c.quality, (KINDS.get(c.quality), []))
    if kind is None:                                    # a quality with no MusicXML kind: kept as its text
        ET.SubElement(h, "kind", text=c.quality).text = "other"
    else:
        ET.SubElement(h, "kind").text = kind
    if c.bass:
        bass = ET.SubElement(h, "bass")
        ET.SubElement(bass, "bass-step").text = c.bass
        if c.bass_alter:
            ET.SubElement(bass, "bass-alter").text = str(c.bass_alter)
    for value, alter, how in degrees:
        d = ET.SubElement(h, "degree")
        ET.SubElement(d, "degree-value").text = str(value)
        ET.SubElement(d, "degree-alter").text = str(alter)
        ET.SubElement(d, "degree-type").text = how
    if offset:
        ET.SubElement(h, "offset").text = str(offset)
    if staff_no:
        ET.SubElement(h, "staff").text = staff_no
    return h


def attach(xml: str, chords: list[Chord], layout: dict) -> tuple[str, int]:
    """The page's MusicXML with each chord symbol written before the note it stands over; and how many were
    placed. A symbol over a held note, between two notes, is written at its share of the way through the note."""
    if not chords:
        return xml, 0
    head, body = xml.split("<score-partwise", 1)
    root = ET.fromstring("<score-partwise" + body)
    # the notes that can carry a symbol: located, not the upper notes of a chord, by staff and from left to right
    by_staff: dict[int, list] = {}
    for part in root.findall("part"):
        for meas in part.findall("measure"):
            for note in meas.findall("note"):
                if note.get("ds") is not None and note.find("chord") is None and note.find("grace") is None:
                    by_staff.setdefault(int(note.get("ds")), []).append((float(note.get("dx")), note, meas))
    # engravers set a symbol either from its note head's left edge or centred over the note: whichever puts this
    # page's symbols nearer to notes
    def at(c: Chord, centred: bool) -> float:
        return (c.x + c.x1) / 2 if centred else c.x + 0.6 * layout["staves"][c.staff]["sp"]

    def miss(centred: bool) -> float:
        return sum(min(abs(n[0] - at(c, centred)) for n in by_staff[c.staff]) for c in chords if by_staff.get(c.staff))

    centred = miss(True) < miss(False)
    placed = 0
    for c in chords:
        notes = sorted(by_staff.get(c.staff, []), key=lambda n: n[0])
        if not notes:
            continue
        sp = layout["staves"][c.staff]["sp"]
        x = at(c, centred)
        # the note it stands on: the nearer of the one before and the one after, when it is close to either
        before = [k for k in range(len(notes)) if notes[k][0] <= x]
        i = before[-1] if before else 0
        if i + 1 < len(notes) and notes[i + 1][0] - x < x - notes[i][0]:
            i += 1
        offset = 0
        if before and abs(notes[i][0] - x) > ON_NOTE * sp:
            # between two notes, close to neither: it changes while the earlier note is held, at its share of
            # the way to the next note (or, for the bar's last note, to about where the bar ends)
            i = before[-1]
            same_bar = i + 1 < len(notes) and notes[i + 1][2] is notes[i][2]
            end = notes[i + 1][0] if same_bar else \
                (notes[i + 1][0] - 2 * sp if i + 1 < len(notes) and notes[i + 1][0] > x else
                 layout["staves"][c.staff]["x1"])
            dur = int(notes[i][1].findtext("duration") or 0)
            share = round(4 * (x - notes[i][0]) / max(1.0, end - notes[i][0])) / 4
            if 0 < share < 1 and dur * share == int(dur * share):
                offset = int(dur * share)
        _, note, meas = notes[i]
        meas.insert(list(meas).index(note), _harmony(c, note.findtext("staff"), offset))
        placed += 1
    return head + ET.tostring(root, encoding="unicode") + "\n", placed


def read(png: Path, xml: Path, layout: dict) -> list[Chord]:
    """The page's chord symbols, found once and kept beside its MusicXML."""
    kept = xml.with_suffix(".chords.json")
    if kept.exists():
        return [Chord(**c) for c in json.loads(kept.read_text())]
    found = find(png, layout)
    kept.write_text(json.dumps([asdict(c) for c in found]))
    return found
