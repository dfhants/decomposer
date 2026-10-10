---
name: decompose
description: Convert sheet music into an editable score - a PDF, scanned pages, photos or screenshots of a score, or a folder of them, become MusicXML plus a MuseScore .mscz file. Runs locally with the copista OMR model.
when_to_use: Use when the user asks to convert, scan, transcribe, digitise, import or "OMR" sheet music, or to get a score PDF or image into MuseScore, MusicXML, Sibelius, Dorico or Finale. Not for audio, and not for writing or arranging music.
argument-hint: "[PDF, images or a folder]"
allowed-tools: Bash(decomposer *), Read
---

# Convert sheet music to an editable score

Everything goes through the `decomposer` command, which this plugin puts on the PATH. It runs on this machine;
nothing is uploaded. Input to convert: $ARGUMENTS

Setup state right now: !`"${CLAUDE_PLUGIN_ROOT}/bin/decomposer" status 2>&1 || true`

If that says "not set up", tell the user what the first run will download before you run anything, then go on:
the first `decomposer` command sets itself up. If it lists missing tools, ask before installing them.

## 1. Find the pages

If the user has not said which files, ask. A folder stands for every PDF and image in it. If you are unsure
which files in a folder belong to the piece, list it and ask rather than converting everything.

## 2. Inspect before converting

```
decomposer inspect <files or folder>
```

This costs a second and catches the two things that ruin a conversion:

- **Page order.** Read the contact sheet it prints: the top of every page, labelled in the order they will be
  read. The printed page numbers and the bar number at the start of each page must run upwards. Files named
  "page 8" and "page 9" are sometimes the other way round. If the order is wrong, pass the files to `convert`
  one by one in the right order instead of passing the folder.
- **Resolution.** A page marked `poor` will convert with many wrong notes. Say so before converting and ask
  whether there is a larger scan or the original PDF; convert anyway if that is all there is.

While the contact sheet is open, note the title, the composer and the names printed beside the staves of the
first full system: they go into `convert`. Use only what is printed. If the staves are not labelled, leave
`--parts` out rather than guessing.

A page that is not music (a cover, a blank) should be left out of the file list.

## 3. Convert

```
decomposer convert <files in order> --title "Title" --composer "Name" --parts "Soprano,Alto,Piano" --out <folder>
```

- `--parts` names the parts from the top staff down, comma-separated. A piano's two staves are one part.
- The result is `<title>.musicxml` and `<title>.mscz`, in the folder of the first input unless `--out` says
  otherwise. `--name` sets the file name when it should differ from the title.
- An image wider than it is tall is cut into two facing pages. Pass `--no-split` for a single landscape page.
- Chord symbols printed above the staves ("Dm7", "G/B") are read and written into the score. Pass `--no-chords`
  to leave them out.
- About 6 seconds a page, the first one longer. Pages are cached: converting again, or with other options, is
  instant.

It prints one line per page - systems, bars, parts, chord symbols - and then any warnings. Read them:

- Bars per page should look like the source. A page with about twice the bars of its neighbours has had a
  system split in two; a page with far fewer has lost one.
- Every page should have the same number of parts. A warning names the pages that differ.
- If the source has chord symbols, every page that shows them should report some. A page with none, or far
  fewer than its neighbours, has had a line missed.

## 4. Check the result

Do not call the result accurate without looking at it.

```
decomposer render "<the .musicxml file>"
```

prints one image per page of the engraved result; page N is page N of the source, whose images are in the
"page images" folder `convert` printed. Read one source page and its rendered page together and compare bar by
bar. Check at least the first page, one page from the middle, and every page a warning named. Look for: the
clef and key at the start, parts on the right staves (a piano introduction in the piano, not in the voices),
the same number of bars per system, the notes of a few bars, and, where the source has chord symbols, that each
one is there, spelled the same, over the same beat.

## 5. Report

Tell the user, briefly:

- where the `.musicxml` and `.mscz` files are;
- which pages you compared and what you found, including errors - name the bars;
- that **lyrics are not transcribed**, if the music has any, and that fingering is not either;
- how many chord symbols were read, if any, and any you saw missing or misplaced;
- any warnings, in plain words.

Offer to open the score in MuseScore (`open "<file>.mscz"`) or the side-by-side viewer in the browser
(`open "<viewer path>"`, which shows each scan with the symbols that were detected). Do not open them unasked.

## When something goes wrong

- **Wrong page order in the result**: convert again with the files listed in the right order. It is instant.
- **A page that is plainly wrong** (parts on the wrong staves, bars doubled): say which page and what you see.
  Do not hand-edit the MusicXML to hide it.
- **"musescore: not written"**: MuseScore 4 is not installed or could not read the file. The `.musicxml` is
  still good and opens in any notation program.
- **Handwritten music** mostly does not work. Say so rather than presenting a bad result as a conversion.
