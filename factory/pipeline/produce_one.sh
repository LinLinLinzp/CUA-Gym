#!/usr/bin/env bash
# Prepare or produce one Computer MCP task. Reuse the batch name to retry that plan.
set -euo pipefail
cd "$(dirname "$0")/../.."
stage=${1:-}
batch=${2:-}
if [[ $# -ne 2 || ! $stage =~ ^(prepare|run)$ || ! $batch =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "Usage: bash factory/pipeline/produce_one.sh {prepare|run} <batch-name>" >&2
  exit 2
fi
plan="output/harbor/plan/$batch.jsonl"
if [[ ! -e $plan ]]; then
  python3 factory/pipeline/allocate.py --total 1 --seed "${PLAN_SEED:-7}" --out "$plan"
fi
mapfile -t fields < <(python3 - "$plan" <<'PY'
import json, sys
from pathlib import Path
plan = Path(sys.argv[1])
rows = [json.loads(line) for line in plan.read_text().splitlines() if line.strip()]
if len(rows) != 1 or rows[0]["slot_id"] != plan.stem + "-s001":
    sys.exit("Expected exactly one slot assigned to this batch.")
print(rows[0]["slot_id"])
for site in rows[0]["sites"]:
    print(site)
PY
)
if (( ${#fields[@]} < 2 )); then
  echo "No usable slot in $plan" >&2
  exit 1
fi
slot=${fields[0]}
if [[ $stage == prepare ]]; then
  python3 factory/hub_tools/build_dists.py "${fields[@]:1}"
  echo "Plan: $plan"
  echo "Slot: $slot"
  exit 0
fi
: "${CODEX_MODEL:?Set CODEX_MODEL to a model enabled for your account}"
command -v "${CODEX_BIN:-codex}" >/dev/null || { echo "Codex CLI missing in this shell" >&2; exit 1; }
docker info >/dev/null
docker compose version >/dev/null
if [[ $("${HARBOR_BIN:-harbor}" --version) != 0.1.45 ]]; then
  echo "Set HARBOR_BIN to the Harbor 0.1.45 executable" >&2
  exit 1
fi
python3 factory/pipeline/run_batch.py "$plan" --only "$slot" --workers 1 --retry \
  --engine codex --codex-model "$CODEX_MODEL" --runtime computer-mcp
python3 - "$plan" "$slot" <<'PY'
import json, sys
from pathlib import Path
plan, slot = Path(sys.argv[1]), sys.argv[2]
record = json.loads(plan.with_suffix(".status.json").read_text())[slot]
if record["state"] != "packaged":
    print(json.dumps(record, ensure_ascii=False, indent=2), file=sys.stderr)
    sys.exit(f"See output/harbor/logs/{slot}.log")
print(f"Task: factory/tasks_src/{slot}")
print(f"Archive: output/harbor/tars/{slot}-computer-mcp.tar.gz")
PY
