import xml.etree.ElementTree as ET

from decomposer.chords import Chord, attach, parse
from decomposer.engine import clean


def chord(word):
    c = parse(word)
    return c and (c["root"], c["root_alter"], c["quality"], c["bass"], c["bass_alter"])


def test_plain_symbols():
    assert chord("G") == ("G", 0, "", "", 0)
    assert chord("Bbm7") == ("B", -1, "m7", "", 0)
    assert chord("F#dim") == ("F", 1, "dim", "", 0)
    assert chord("D/F#") == ("D", 0, "", "F", 1)
    assert chord("C(add9)") == ("C", 0, "add9", "", 0)


def test_what_a_recogniser_makes_of_them():
    assert chord("E♭maj7") == ("E", -1, "maj7", "", 0)
    assert chord("Bm765") == ("B", 0, "m7b5", "", 0)            # a flat sign read as a 6
    assert chord("F(suS2)") == ("F", 0, "sus2", "", 0)          # small capitals in any case
    assert chord("CS") == ("C", 0, "5", "", 0)                  # a superscript 5 read as an S
    assert chord("C/Е") == ("C", 0, "", "E", 0)                 # a Cyrillic letter for a Latin one
    assert parse("G(SUS4)")["text"] == parse("G(sus4)")["text"] == "Gsus4"


def test_words_are_not_symbols():
    for word in ("Verses", "Be", "Hall", "I", "the", "12", "N.C.", "Chorus"):
        assert parse(word) is None


PAGE = """<?xml version="1.0"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>V</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>2</divisions></attributes>
<note dx="100.0" ds="0"><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration></note>
<note dx="200.0" ds="0"><pitch><step>D</step><octave>4</octave></pitch><duration>2</duration></note>
<note dx="200.0" ds="0"><chord /><pitch><step>F</step><octave>4</octave></pitch><duration>2</duration></note>
<note dx="300.0" ds="0"><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration></note>
</measure></part></score-partwise>"""
LAYOUT = {"staves": [{"y0": 100, "y1": 140, "x0": 50, "x1": 520, "sp": 10, "system": 0}]}


def symbol(word, x, width=20):
    return Chord(x=x, x1=x + width, staff=0, **parse(word))


def placed(chords):
    xml, n = attach(PAGE, chords, LAYOUT)
    measure = ET.fromstring(clean(xml).split("?>", 1)[1]).find("part/measure")
    out, at = [], 0
    for el in measure:
        if el.tag == "harmony":
            out.append((el.findtext("root/root-step"), el.findtext("kind"), at + int(el.findtext("offset") or 0)))
        elif el.tag == "note" and el.find("chord") is None:
            at += int(el.findtext("duration"))
    return n, out


def test_a_symbol_is_written_before_the_note_under_it():
    # left edges at the note heads' left edges; the second stands over a chord's lowest note
    assert placed([symbol("G", 94), symbol("Dm", 194)]) == (2, [("G", "major", 0), ("D", "minor", 2)])


def test_centred_symbols_are_placed_by_their_middles():
    assert placed([symbol("Cmaj7", 60, 80), symbol("F", 290)]) == (2, [("C", "major-seventh", 0), ("F", "major", 4)])


def test_a_symbol_over_a_held_note_is_offset_into_it():
    # the last note lasts 4 from x=300 to the staff's end at 520: a symbol half way changes after 2
    assert placed([symbol("G", 94), symbol("A7", 404)]) == (2, [("G", "major", 0), ("A", "dominant", 6)])


def test_the_note_positions_are_taken_out_again():
    xml, _ = attach(PAGE, [symbol("G", 94)], LAYOUT)
    assert "dx=" in xml and "dx=" not in clean(xml) and "ds=" not in clean(xml)
