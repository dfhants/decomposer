#!/bin/sh
# Set up or update the model's home: the copista reader at a pinned commit with our patches, its Python
# environment, and the model weights at a pinned revision. Each step is skipped when already done.
#   setup.sh <plugin root> <home>
set -e
ROOT="$1"
HOME_DIR="$2"

COPISTERIA_REV=fbc5ab60d5b7a7b69a8a287bab068b0eceb20f69
# The weights are loaded with torch.load, which runs code in the file. Pinning the revision means a later change
# to the Hugging Face repository cannot reach this machine without this line being changed.
WEIGHTS_REPO=kobimusic/copista-28m
WEIGHTS_REV=44464d11234a22ba23634ec8eb1e31e3b012021a

mkdir -p "$HOME_DIR"
SRC="$HOME_DIR/copisteria"

if [ ! -d "$SRC/.git" ]; then
    echo "setup: fetching the copista reader"
    git clone --quiet https://github.com/kobimusic/copisteria.git "$SRC"
fi
git -C "$SRC" cat-file -e "$COPISTERIA_REV" 2>/dev/null || git -C "$SRC" fetch --quiet origin
git -C "$SRC" reset --quiet --hard "$COPISTERIA_REV"
for patch in "$ROOT"/patches/*.patch; do
    git -C "$SRC" apply "$patch"
done

if [ ! -x "$HOME_DIR/venv/bin/python" ]; then
    echo "setup: creating the Python environment"
    uv venv --quiet --python 3.12 "$HOME_DIR/venv"
fi
echo "setup: installing Python packages"
uv pip install --quiet --python "$HOME_DIR/venv/bin/python" -r "$ROOT/core/requirements.txt" -e "$SRC"

if [ ! -f "$SRC/models/evidence-2m.pt" ] || [ ! -f "$SRC/models/small/v7_obj-recall-30m_best.pt" ]; then
    echo "setup: downloading the model weights (about 125 MB)"
    "$HOME_DIR/venv/bin/hf" download "$WEIGHTS_REPO" --revision "$WEIGHTS_REV" --include "*.pt" \
        --local-dir "$SRC/models" >/dev/null
fi
echo "setup: done"
