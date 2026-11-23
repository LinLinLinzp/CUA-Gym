#!/usr/bin/env bash
# Keep the lever experiments moving while mocks are still being built: every 20 min,
# refresh the catalog, plan slots for levers that now have suitable new sites, and
# generate any unfinished slots. Stops once all 16 levers are planned and run.
set -uo pipefail
cd "$(dirname "$0")/.."
PLAN=../output/harbor/plan/exp1.jsonl
while true; do
  python3 catalog/build_catalog.py > /dev/null
  python3 pipeline/plan_experiments.py --out "$PLAN"
  [ -f "$PLAN" ] && python3 pipeline/run_batch.py "$PLAN" --workers 2 --rounds 3
  planned=$( [ -f "$PLAN" ] && wc -l < "$PLAN" || echo 0 )
  if [ "$planned" -ge 16 ]; then echo "all levers planned and run"; break; fi
  sleep 1200
done
