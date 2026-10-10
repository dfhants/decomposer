# decomposer

Turns sheet music (PDFs, scans, screenshots) into editable MusicXML and MuseScore files. It runs locally with the
[copista](https://github.com/kobimusic/copisteria) OMR model, and is packaged as a Claude Code plugin.

## Use it from Claude Code

```
claude plugin marketplace add dfhants/decomposer
claude plugin install decomposer@decomposer
```

Then ask Claude to convert a score, or run `/decomposer:decompose <files or folder>`.

## Use it from chat in the Claude desktop app

Build the desktop extension and open it; the app asks to install it.

```
python3 desktop/build.py        # writes dist/decomposer.mcpb; needs npx
open dist/decomposer.mcpb
```

Then give Claude the path of a score in any chat. The extension is an MCP server (`desktop/server.py`) that
drives the same `decomposer` command and hands the contact sheet and page pictures back to Claude. It works on
paths on your Mac: a file dragged into the chat is not on disk. It does not work in a browser or on a phone.

## Use it from a terminal

```
bin/decomposer inspect ~/Scans/piece          # page order, resolution, contact sheet
bin/decomposer convert ~/Scans/piece --title "Piece" --parts "Voice,Piano"
bin/decomposer render ~/Scans/piece/Piece.musicxml
```

The first command sets up the model in `~/Library/Application Support/decomposer` (about 125 MB of weights and a
1 GB Python environment). Page caches are in `~/Library/Caches/decomposer`. Deleting either folder is safe; they
are rebuilt on the next run. Needs macOS, `uv`, `git` and poppler; MuseScore 4 for `.mscz` output and `render`.

## What it does beyond copista

- Cuts two-page spreads apart and joins the pages into one score.
- Three patches to copista's layout (`patches/copisteria.patch`) for choral scores: a faint system line counts as
  one, half-systems are joined when the page's other systems show they belong together, and a system with hidden
  staves is lined up by its brace instead of from the top.

Lyrics are not read.

## Develop

```
PYTHONPATH=core uv run --no-project --python 3.12 --with pytest pytest core/tests
```

Changing `patches/`, `scripts/setup.sh` or `core/requirements.txt` makes the next run update the model's home and
re-read cached pages.

## Licence and credits

Apache-2.0. The recognition is done entirely by [copisteria](https://github.com/kobimusic/copisteria) and the
copista model, by KobiMusic. Neither is included here: both are downloaded on first run. See `NOTICE`.
