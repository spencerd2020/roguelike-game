#!/bin/bash
# Copy a kit build into the page folder as artifact-servable files: <name>.json (glTF, embedded) and <name>.info.json
SRC=$1; DST=${2:-"$(dirname "$0")/../page/kit"}
mkdir -p "$DST"
for g in "$SRC"/*.glb; do n=$(basename "$g" .glb); python3 "$(dirname "$0")/glb2json.py" "$g" "$DST/$n.gltf.json"; cp "$SRC/$n.json" "$DST/$n.info.json"; done
ls "$DST" | wc -l
