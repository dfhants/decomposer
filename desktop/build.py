#!/usr/bin/env python3
"""Make dist/decomposer.mcpb, the one-file installer for the Claude desktop app.

    python3 desktop/build.py        # needs npx (Node), for the packer

The bundle carries the MCP server and the decomposer command it drives (bin/, core/, scripts/, patches/). The
desktop app runs the server with uv. The model is not in the bundle: the command sets it up on first use.
"""
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STAGE = ROOT / "dist" / "mcpb"
OUT = ROOT / "dist" / "decomposer.mcpb"

shutil.rmtree(STAGE, ignore_errors=True)
STAGE.mkdir(parents=True)
skip = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "tests")
for folder in ("bin", "core", "scripts", "patches"):
    shutil.copytree(ROOT / folder, STAGE / folder, ignore=skip)
for file in (HERE / "server.py", HERE / "pyproject.toml", ROOT / "LICENSE", ROOT / "NOTICE"):
    shutil.copyfile(file, STAGE / file.name)
manifest = json.loads((HERE / "manifest.json").read_text())
plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
manifest["version"] = plugin["version"]             # the plugin manifest says what version this is
(STAGE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
subprocess.run(["npx", "--yes", "@anthropic-ai/mcpb", "pack", str(STAGE), str(OUT)], check=True)
print(OUT)
