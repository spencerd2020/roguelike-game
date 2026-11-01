#!/bin/bash
# Build the jungle kit, two at a time on a four-core box: python3 jungle_kit.py per model, then fix_seams.py.
OUT=${1:-../kit}; shift
cd "$(dirname "$0")"
export FURN_DIR=$(realpath ../page/props)
LIST=${@:-"stilthouse sky-1 4096|stilthouse sky-2 4096|stilthouse sky-3 4096|stilthouse sky-4 4096|longhouse long-1 4096|granary store-1 2048|granary store-2 2048|shrine spirit-1 1024|waterwheel wheel-1 2048|emergent e-1 2048|emergent e-2 2048|emergent e-3 2048|banyan fig-1 4096|bamboo bam-1 2048|bamboo bam-2 2048|banana ban-1 1024|banana ban-2 1024|taro taro-1 1024|treefern fern-1 1024|treefern fern-2 1024|karst karst-1 4096|karst karst-2 4096|boulders stones-1 2048"}
run() { set -- $1; PREV_SAMPLES=24 python3 jungle_kit.py --asset $1 --seed $2 --size $3 --samples 16 --out "$OUT" --render > "$OUT/log_$1_$2.txt" 2>&1 \
  && python3 fix_seams.py "$OUT/$1_$2.glb" --png "$OUT/$1_$2_atlas.png" >> "$OUT/log_$1_$2.txt" 2>&1; echo "$1 $2 exit $?"; }
export -f run; export OUT
echo "$LIST" | tr '|' '\n' | xargs -P 2 -I{} bash -c 'run "{}"'
