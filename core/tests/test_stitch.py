import xml.etree.ElementTree as ET

from decomposer.stitch import stitch


def page(parts: int, measures: int, key: int = 0, clef: str = "G") -> str:
    """A page's score: ``parts`` parts of ``measures`` measures in 3/4, each holding one dotted half note."""
    names = "".join(f'<score-part id="P{i}"><part-name>Part {i}</part-name></score-part>' for i in range(1, parts + 1))
    body = ""
    for i in range(1, parts + 1):
        ms = ""
        for n in range(1, measures + 1):
            attrs = (f"<attributes><divisions>2</divisions><key><fifths>{key}</fifths></key>"
                     f"<time><beats>3</beats><beat-type>4</beat-type></time>"
                     f"<clef><sign>{clef}</sign><line>2</line></clef></attributes>") if n == 1 else ""
            ms += (f'<measure number="{n}">{attrs}<note><pitch><step>C</step><octave>4</octave></pitch>'
                   f"<duration>6</duration><voice>1</voice></note></measure>")
        body += f'<part id="P{i}">{ms}</part>'
    return f'<score-partwise version="4.0"><part-list>{names}</part-list>{body}</score-partwise>'


def parts_of(xml: str) -> list[list[ET.Element]]:
    return [p.findall("measure") for p in ET.fromstring(xml.split("\n", 2)[2]).findall("part")]


def test_measures_are_appended_and_numbered_through():
    parts = parts_of(stitch([page(2, 3), page(2, 4)]))
    assert [len(p) for p in parts] == [7, 7]
    assert [m.get("number") for m in parts[0]] == [str(n) for n in range(1, 8)]


def test_a_restated_signature_is_dropped_and_a_changed_one_kept():
    same = parts_of(stitch([page(1, 2), page(1, 2)]))[0][2]
    assert same.find("attributes/key") is None and same.find("attributes/clef") is None
    assert same.findtext("attributes/divisions") == "2"
    changed = parts_of(stitch([page(1, 2), page(1, 2, key=-3)]))[0][2]
    assert changed.findtext("attributes/key/fifths") == "-3"
    assert changed.find("attributes/time") is None


def test_each_later_page_starts_a_new_page():
    parts = parts_of(stitch([page(1, 2), page(1, 2)]))
    assert parts[0][2].find("print").get("new-page") == "yes"
    assert parts[0][0].find("print") is None


def test_a_page_with_fewer_parts_fills_the_bottom_ones_and_rests_the_rest():
    top, bottom = parts_of(stitch([page(2, 2), page(1, 3)]))
    assert len(top) == len(bottom) == 5
    assert all(m.find("note/rest") is not None for m in top[2:])
    assert top[2].findtext("note/duration") == "6"          # a bar of 3/4 at 2 divisions
    assert all(m.find("note/pitch") is not None for m in bottom)


def test_a_part_that_enters_later_rests_until_then():
    xml = stitch([page(1, 2), page(2, 2)])
    top, bottom = parts_of(xml)
    assert len(top) == len(bottom) == 4
    assert all(m.find("note/rest") is not None for m in top[:2])
    assert all(m.find("note/pitch") is not None for m in top[2:] + bottom)
    ids = [sp.get("id") for sp in ET.fromstring(xml.split("\n", 2)[2]).find("part-list")]
    assert ids == ["P1", "P2"]


def test_an_unprinted_meter_restated_is_still_dropped():
    second = page(1, 2).replace("<time>", '<time print-object="no">')
    assert parts_of(stitch([page(1, 2), second]))[0][2].find("attributes/time") is None


def test_a_part_that_enters_later_opens_in_its_own_clef_and_key():
    top = parts_of(stitch([page(1, 2), page(2, 2, key=2, clef="F")]))[0]
    assert top[0].findtext("attributes/clef/sign") == "F"
    assert top[0].findtext("attributes/key/fifths") == "2"
    assert top[2].find("attributes/clef") is None and top[2].find("attributes/key") is None


def test_title_composer_and_part_names_are_written():
    xml = stitch([page(2, 1)], title="A Song", composer="A. Composer", part_names=["Voice", "Piano"])
    root = ET.fromstring(xml.split("\n", 2)[2])
    assert root.findtext("work/work-title") == "A Song"
    assert root.findtext("identification/creator") == "A. Composer"
    assert [sp.findtext("part-name") for sp in root.find("part-list")] == ["Voice", "Piano"]
    assert [c.tag for c in root][:3] == ["work", "identification", "part-list"]
