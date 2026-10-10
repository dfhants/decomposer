"""Join the pages' MusicXML into one score.

copisteria writes each page as its own score. Here the pages' measures are appended part by part, the measures
numbered through, and a clef, key or time signature a page restates unchanged is dropped. Pages need not show the
same parts (a piano introduction before the choir enters): parts are matched from the bottom of the system up,
where the accompaniment sits, and a part a page does not show rests through it.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction

HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">\n')
RESTATED = ("key", "time", "clef")


@dataclass
class State:
    """What a part's last measure left standing."""
    divisions: int = 1
    time: tuple[int, int] = (4, 4)
    signs: dict = field(default_factory=dict)       # (tag, staff number) -> the element as text


ORDER = ("divisions", "key", "time", "staves", "clef")      # the order MusicXML wants inside <attributes>


def _text(el: ET.Element) -> str:
    """The sign as text, whether or not it is printed: a meter a page leaves unprinted is the same meter."""
    el = copy.deepcopy(el)
    el.attrib.pop("print-object", None)
    return "".join(ET.tostring(el, encoding="unicode").split())


def _hoist(measures: list[ET.Element]) -> None:
    """A part that rests before it first plays (the choir under a piano introduction) gets its clef and key only
    where it enters, and would open in a default clef that then changes. Give them to its first measure."""
    entry = next((i for i, m in enumerate(measures) if m.find("note/pitch") is not None), 0)
    if entry == 0:
        return
    found = [el for m in measures[:entry + 1] for a in m.findall("attributes") for el in a
             if el.tag in ("key", "staves", "clef")]
    if not found:
        return
    for m in measures[:entry + 1]:
        for a in m.findall("attributes"):
            for el in [el for el in a if el in found]:
                a.remove(el)
            if len(a) == 0:
                m.remove(a)
    latest = {(el.tag, el.get("number", "1")): el for el in found}       # the signs standing at the entry
    first = measures[0].find("attributes")
    if first is None:
        first = ET.Element("attributes")
        measures[0].insert(1 if measures[0].find("print") is not None else 0, first)
    kept = [el for el in first if el.tag not in ("key", "staves", "clef")] + list(latest.values())
    for el in list(first):
        first.remove(el)
    first.extend(sorted(kept, key=lambda el: (ORDER.index(el.tag) if el.tag in ORDER else len(ORDER),
                                              el.get("number", "1"))))


def _absorb(state: State, measure: ET.Element, page_start: bool) -> None:
    """Update ``state`` with the measure's attributes; at a page's start, drop the signs it only restates."""
    for attrs in measure.findall("attributes"):
        div = attrs.find("divisions")
        if div is not None:
            state.divisions = int(div.text)
        for el in list(attrs):
            if el.tag not in RESTATED:
                continue
            key, text = (el.tag, el.get("number", "1")), _text(el)
            if page_start and state.signs.get(key) == text:
                attrs.remove(el)
            state.signs[key] = text
            if el.tag == "time" and el.find("beats") is not None:
                try:
                    state.time = (int(el.findtext("beats")), int(el.findtext("beat-type")))
                except ValueError:
                    pass
        if len(attrs) == 0:
            measure.remove(attrs)


def _rest(state: State, first: bool = False) -> ET.Element:
    """A measure of rest in the part's meter (``first``: for a part that has no measure yet)."""
    m = ET.Element("measure", number="0")
    if first:
        attrs = ET.SubElement(m, "attributes")
        ET.SubElement(attrs, "divisions").text = str(state.divisions)
        time = ET.SubElement(attrs, "time")
        ET.SubElement(time, "beats").text = str(state.time[0])
        ET.SubElement(time, "beat-type").text = str(state.time[1])
    note = ET.SubElement(m, "note")
    ET.SubElement(note, "rest", measure="yes")
    ET.SubElement(note, "duration").text = str(int(Fraction(state.divisions * 4 * state.time[0], state.time[1])))
    ET.SubElement(note, "voice").text = "1"
    return m


def _new_page(measure: ET.Element) -> None:
    pr = measure.find("print")
    if pr is None:
        pr = ET.Element("print")
        measure.insert(0, pr)
    pr.set("new-page", "yes")


def _label(score: ET.Element, entries: list, title, composer, parts) -> None:
    """The score's title and composer, and its parts' names from the top down."""
    if title:
        work = score.find("work")
        if work is None:
            work = ET.Element("work")
            score.insert(0, work)
        for old in work.findall("work-title"):
            work.remove(old)
        ET.SubElement(work, "work-title").text = title
    if composer:
        ident = score.find("identification")
        if ident is None:
            ident = ET.Element("identification")
            score.insert(list(score).index(score.find("part-list")), ident)
        for old in ident.findall("creator"):
            ident.remove(old)
        creator = ET.Element("creator", type="composer")
        creator.text = composer
        ident.insert(0, creator)
    for entry, name in zip(entries, parts or []):
        entry.find("part-name").text = name


def stitch(pages: list[str], title: str | None = None, composer: str | None = None,
           part_names: list[str] | None = None) -> str:
    """One MusicXML score from the pages' scores, in order."""
    if not pages:
        raise ValueError("no pages to join")
    score = ET.fromstring(pages[0])
    part_list = score.find("part-list")
    parts = score.findall("part")
    names = {sp.get("id"): sp for sp in part_list.findall("score-part")}
    entries = [names[p.get("id")] for p in parts]
    states = [State() for _ in parts]
    for part, state in zip(parts, states):
        for m in part.findall("measure"):
            _absorb(state, m, False)

    for xml in pages[1:]:
        page = ET.fromstring(xml)
        new = page.findall("part")
        if not new:
            continue
        new_names = {sp.get("id"): sp for sp in page.find("part-list").findall("score-part")}
        length = max(len(p.findall("measure")) for p in new)
        so_far = max((len(p.findall("measure")) for p in parts), default=0)
        # a part this page shows above every part so far: it rested until now
        for extra in reversed(new[:max(0, len(new) - len(parts))]):
            part = ET.Element("part")
            state = State(divisions=states[-1].divisions, time=states[-1].time) if states else State()
            for i in range(so_far):
                part.append(_rest(state, first=i == 0))
            score.insert(list(score).index(parts[0]) if parts else len(score), part)
            parts.insert(0, part)
            states.insert(0, state)
            entries.insert(0, copy.deepcopy(new_names[extra.get("id")]))
        offset = len(parts) - len(new)
        for i, (part, state) in enumerate(zip(parts, states)):
            measures = new[i - offset].findall("measure") if i >= offset else []
            for j in range(length):
                m = measures[j] if j < len(measures) else _rest(state)
                _absorb(state, m, j == 0)
                if j == 0:
                    _new_page(m)
                part.append(m)

    for sp in list(part_list.findall("score-part")):
        part_list.remove(sp)
    for i, (part, entry) in enumerate(zip(parts, entries), 1):
        part.set("id", f"P{i}")
        entry.set("id", f"P{i}")
        part_list.append(entry)
        _hoist(part.findall("measure"))
        for n, m in enumerate(part.findall("measure"), 1):
            m.set("number", str(n))
    _label(score, entries, title, composer, part_names)
    ET.indent(score)
    return HEAD + ET.tostring(score, encoding="unicode") + "\n"
