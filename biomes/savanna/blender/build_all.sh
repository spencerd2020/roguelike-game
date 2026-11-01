#!/bin/bash
# Build the whole savanna kit: two at a time on a four-core box.
OUT=${1:-../out}
cd "$(dirname "$0")"
jobs_list=(
 "house hearth-1 4096" "house hearth-2 4096" "house hearth-3 4096" "greathouse great-1 4096"
 "granary store-1 2048" "pavilion shade-1 2048" "thorn thorn-1 2048" "thorn thorn-2 2048" "thorn thorn-3 2048"
 "bottle bottle-1 2048" "bottle bottle-2 2048" "kopje kopje-1 4096" "mound mound-1 1024" "mound mound-2 1024" "boulders stones-1 2048"
)
run() { set -- $1; python3 savanna_kit.py --asset $1 --seed $2 --size $3 --samples 16 --out "$OUT" --render > "$OUT/log_$1_$2.txt" 2>&1 \
  && python3 fix_seams.py "$OUT/$1_$2.glb" --png "$OUT/$1_$2_atlas.png" >> "$OUT/log_$1_$2.txt" 2>&1; echo "$1 $2 exit $?"; }
export -f run; export OUT
printf '%s\n' "${jobs_list[@]}" | xargs -P 2 -I{} bash -c 'run "{}"'
