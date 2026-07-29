#!/usr/bin/env bash
#
# Reproducible CodeSwarm evaluation harness.
#
# Builds each example spec with the swarm, then INDEPENDENTLY re-runs each
# generated project's own test-suite to prove the code is really green (not just
# that the swarm said so). Prints a compact PASS/FAIL summary at the end.
#
# Usage:
#   scripts/run_eval.sh --dry-run                 # offline smoke test (no API key)
#   scripts/run_eval.sh --provider byteplus       # against BytePlus ModelArk
#   scripts/run_eval.sh --provider byteplus --model <your-modelark-model-id>
#
# Any extra args (e.g. --provider, --model, --sequential) are passed straight
# through to `codeswarm build`.
#
# Prereqs: run inside your venv with `pip install -e .`, and for a real provider
# set the matching API key (e.g. ARK_API_KEY) — see .env.example.

set -uo pipefail

OUT="${OUT:-./output}"

# spec:project-name (name must match the `name:` field in each spec)
ENTRIES=(
  "examples/todo_api.yaml:todo-core"
  "examples/password_strength.yaml:password-strength"
  "examples/csv_stats.yaml:csv-stats"
)

results=()

for entry in "${ENTRIES[@]}"; do
  spec="${entry%%:*}"
  name="${entry##*:}"
  echo ""
  echo "=================================================================="
  echo "  Building: $spec"
  echo "=================================================================="
  codeswarm build --spec "$spec" --output "$OUT" "$@"
  build_rc=$?

  if [[ $build_rc -ne 0 ]]; then
    results+=("$name: BUILD-FAILED (swarm reported a failing/blocked feature)")
    continue
  fi

  echo ""
  echo "  Independently re-running generated tests for '$name'..."
  if ( cd "$OUT/$name" && python -m pytest -q >/dev/null 2>&1 ); then
    results+=("$name: PASS (generated tests green)")
  else
    results+=("$name: TESTS-FAILED (generated project did not pass on re-run)")
  fi
done

echo ""
echo "=================================================================="
echo "  Evaluation summary"
echo "=================================================================="
for r in "${results[@]}"; do
  echo "  - $r"
done
