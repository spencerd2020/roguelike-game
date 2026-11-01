#!/bin/bash
# Rebuild the walled models with hand-wound wall faces (correct normals), two at a time.
cd "$(dirname "$0")"; OUT=../kit
run() { set -- $1; python3 savanna_kit.py --asset $1 --seed $2 --size $3 --samples 16 --out "$OUT" --render > "$OUT/log_$1_$2.txt" 2>&1 \
  && python3 fix_seams.py "$OUT/$1_$2.glb" --png "$OUT/$1_$2_atlas.png" >> "$OUT/log_$1_$2.txt" 2>&1; echo "$1 $2 exit $?"; }
export -f run; export OUT
printf '%s\n' "house hearth-1 4096" "house hearth-2 4096" "house hearth-3 4096" "greathouse great-1 4096" "granary store-1 2048" "pavilion shade-1 2048" | xargs -P 2 -I{} bash -c 'run "{}"'
