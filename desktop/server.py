"""decomposer as an MCP server: the same inspect, convert and render as the command line, as tools a chat can call.

It is a thin front: every tool runs the `decomposer` command beside it and hands back what it printed, with the
page images as pictures. The model, its Python environment and the page cache stay where the command keeps them,
so the server itself starts at once and needs only the `mcp` package.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP, Image

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in (HERE, HERE.parent) if (p / "bin" / "decomposer").exists())
COMMAND = str(ROOT / "bin" / "decomposer")
# a desktop app starts its servers with a bare PATH: uv, git and poppler are usually in one of these
ENV = {**os.environ, "PATH": os.pathsep.join([os.environ.get("PATH", ""), "/opt/homebrew/bin", "/usr/local/bin",
                                             str(Path.home() / ".local" / "bin"), str(Path.home() / ".cargo" / "bin")])}
BUDGET = 40             # seconds of reading per convert call: a long score is read over several calls
LONG_SIDE = 1100        # pictures are handed back no larger than this
SETUP_LOG = Path(tempfile.gettempdir()) / "decomposer-setup.log"

mcp = FastMCP("decomposer", instructions="""\
decomposer turns sheet music (PDFs, scans, photos or screenshots of a score) into an editable score: MusicXML
and a MuseScore .mscz file. It runs on the user's own computer; nothing is uploaded. It works on files by their
path on that computer: a file attached to the chat is not on disk, so ask for the path of the file or folder.

Work in this order.
1. `status`. If it is not ready, tell the user what the first run downloads, call `setup`, and call `status`
   again until it says ready.
2. `inspect` the files. Look at the contact sheet it returns: the printed page numbers and the bar number at
   the start of each page must run upwards. If they do not, pass the files to `convert` one by one in the right
   order. If a page is marked poor, say so and ask for a larger scan before converting; convert anyway if that
   is all there is. Note the title, composer and the names printed beside the staves: use only what is printed.
3. `convert`. If it answers that it has read only some of the pages, call it again with the same arguments
   until it finishes. Read its warnings and the bars per page: a page with about twice the bars of its
   neighbours has had a system split in two.
4. Check before calling the result good: `source_pages` and `render` for the same page numbers, compared bar
   by bar. Check the first page, one from the middle, and any page a warning named.
5. Tell the user where the files are, which pages you compared and what you found, and that lyrics, chord
   symbols and fingering are not transcribed. Handwritten music mostly does not work.
""")


def run(*args: str) -> tuple[int, str]:
    done = subprocess.run(["sh", COMMAND, *args], capture_output=True, text=True, env=ENV)
    return done.returncode, (done.stdout + done.stderr).strip()


def ready() -> str | None:
    """None when the model is set up, else what to tell the caller."""
    state = run("status")[1]
    if state.startswith("ready"):
        return None
    return (f"{state}\n\nNot ready to read music yet. Tell the user what will be downloaded, call `setup`, then "
            f"call `status` until it says ready.")


async def command(ctx: Context | None, *args: str) -> dict:
    """Run a decomposer command with --json: its last line is the result, the lines before it are progress."""
    # through sh: a bundle unpacked from a zip may have lost the command's executable bit
    proc = await asyncio.create_subprocess_exec("sh", COMMAND, *args, "--json", env=ENV,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    result: dict = {}
    async for raw in proc.stdout:
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if line.get("event") == "page" and ctx is not None:
            await ctx.report_progress(line["page"], line["of"], f"page {line['page']} of {line['of']}")
        elif line.get("event") == "result":
            result = line
    err = (await proc.stderr.read()).decode().strip()
    await proc.wait()
    if not result:
        result = {"error": err.splitlines()[-1] if err else f"decomposer {args[0]} gave no result"}
    return result


def picture(path: str) -> Image:
    from PIL import Image as Pillow
    with Pillow.open(path) as im:
        im = im.convert("L")
        im.thumbnail((LONG_SIDE, LONG_SIDE))
        data = io.BytesIO()
        im.save(data, "PNG", optimize=True)
    return Image(data=data.getvalue(), format="png")


def paths(files: list[str]) -> list[str] | str:
    """The files as absolute paths, or the reason they cannot be read."""
    out = []
    for f in files:
        p = Path(f).expanduser()
        if not p.exists():
            return (f"{f} is not a file or folder on this computer. A file attached to the chat is not on disk: "
                    f"ask the user for its path.")
        out.append(str(p))
    return out or "give at least one file or folder"


@mcp.tool()
def status() -> str:
    """Whether decomposer is ready to read music, and what is missing if not. Call this first."""
    state = run("status")[1]
    if SETUP_LOG.exists() and not state.startswith("ready"):
        tail = SETUP_LOG.read_text().strip().splitlines()[-3:]
        state += "\n\nsetup log:\n" + "\n".join(tail)
    return state


@mcp.tool()
def setup() -> str:
    """Set up or update the model on this computer, in the background: about 125 MB of model weights and a
    Python environment of about 1 GB, a few minutes. Tell the user before calling it. Call `status` to see
    when it is ready."""
    if ready() is None:
        return "ready"
    log = SETUP_LOG.open("w")
    subprocess.Popen(["sh", COMMAND, "setup"], stdout=log, stderr=subprocess.STDOUT, env=ENV, start_new_session=True)
    return "Setup started. It takes a few minutes. Call `status` every half minute or so until it says ready."


@mcp.tool()
async def inspect(files: list[str], split_spreads: bool = True) -> list:
    """Look at the pages before reading them: their order, size and resolution, and a contact sheet showing the
    top of every page so that the page order can be checked from the printed page and bar numbers.

    files: paths of PDFs, images, or a folder of them, in page order.
    split_spreads: cut an image wider than it is tall into two facing pages."""
    files = paths(files)
    if isinstance(files, str):
        return [files]
    if (why := ready()):
        return [why]
    r = await command(None, "inspect", *files, *([] if split_spreads else ["--no-split"]))
    if "error" in r:
        return [r["error"]]
    return [r["text"], *(picture(s) for s in r["contact_sheets"])]


@mcp.tool()
async def convert(files: list[str], ctx: Context, title: str = "", composer: str = "", parts: list[str] = [],
                  out_folder: str = "", file_name: str = "", split_spreads: bool = True) -> str:
    """Read the pages and write one score: a .musicxml file, and a MuseScore .mscz file when MuseScore 4 is
    installed. About 6 seconds a page. A long score is read over several calls: when the answer says only some
    pages have been read, call again with the same arguments. Pages already read are kept.

    files: paths of PDFs, images, or a folder, in page order (as checked with inspect).
    title, composer: written into the score, as printed on the page.
    parts: part names from the top staff down, as printed; a piano's two staves are one part. Leave empty if
      the staves are not labelled.
    out_folder: where to write the result (default: beside the first file).
    file_name: name of the result without extension (default: the title, else the first file's name)."""
    files = paths(files)
    if isinstance(files, str):
        return files
    if (why := ready()):
        return why
    args = ["convert", *files, "--budget", str(BUDGET)]
    for flag, value in (("--title", title), ("--composer", composer), ("--parts", ",".join(parts)),
                        ("--out", str(Path(out_folder).expanduser()) if out_folder else ""), ("--name", file_name)):
        if value:
            args += [flag, value]
    if not split_spreads:
        args.append("--no-split")
    r = await command(ctx, *args)
    if "error" in r:
        return r["error"]
    if r.get("partial"):
        return f"Read {r['read']} of {r['of']} pages so far. Call convert again with the same arguments to go on."
    lines = [f"page {p['page']}: {p['source']}: {p['systems']} systems, {p['bars']} bars, {p['parts']} parts"
             for p in r["pages"]]
    lines += ["", f"score: {r['musicxml']} ({r['bars']} bars, {r['parts']} parts)",
              f"musescore: {r['mscz']}" if r["mscz"] else
              "musescore: not written (MuseScore 4 is not installed, or it could not read the score)",
              f"side-by-side viewer (open in a browser): {r['viewer']}",
              *(f"warning: {w}" for w in r["warnings"]),
              "Lyrics are not read. Check the result with source_pages and render before calling it good."]
    return "\n".join(lines)


@mcp.tool()
async def source_pages(files: list[str], pages: list[int], split_spreads: bool = True) -> list:
    """Pictures of the source pages as they were read, to compare with `render`. Give the same files, in the
    same order, as to convert. At most 3 pages a call.

    pages: page numbers, counting from 1 in the order inspect listed them."""
    files = paths(files)
    if isinstance(files, str):
        return [files]
    if (why := ready()):
        return [why]
    r = await command(None, "inspect", *files, *([] if split_spreads else ["--no-split"]))
    if "error" in r:
        return [r["error"]]
    out: list = []
    for n in pages[:3]:
        if not 1 <= n <= len(r["pages"]):
            out.append(f"there is no page {n}: the source has {len(r['pages'])} pages")
            continue
        out += [f"source page {n} ({r['pages'][n - 1]['source']})", picture(r["pages"][n - 1]["image"])]
    return out


@mcp.tool()
async def render(score: str, pages: list[int]) -> list:
    """Pictures of the written score, engraved by MuseScore, to compare with the source. A score written by
    convert starts a new page where the source did, so page N here is page N of the source. At most 3 pages a
    call. Needs MuseScore 4.

    score: path of the .musicxml or .mscz file.
    pages: page numbers, counting from 1."""
    found = paths([score])
    if isinstance(found, str):
        return [found]
    if (why := ready()):
        return [why]
    r = await command(None, "render", found[0])
    if "error" in r:
        return [r["error"]]
    out: list = []
    for n in pages[:3]:
        if not 1 <= n <= len(r["images"]):
            out.append(f"there is no page {n}: the score has {len(r['images'])} pages")
            continue
        out += [f"rendered page {n}", picture(r["images"][n - 1])]
    return out


if __name__ == "__main__":
    mcp.run()
