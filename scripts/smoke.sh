#!/usr/bin/env bash
# Real-world smoke test for license-audit.
#
# Downloads lock files from popular open-source Python projects at pinned
# refs and runs license-audit against each. The goal is to catch what unit
# and integration tests cannot: schema drift in real-world lock files,
# unusual metadata shapes, and large dependency graphs that synthetic
# fixtures don't model.
#
# Network required. Run from repo root: ./scripts/smoke.sh
# Exits non-zero if any check fails.

set -euo pipefail

REPO=$(git rev-parse --show-toplevel)
SCRATCH=$(mktemp -d -t license-audit-smoke.XXXXXX)
trap 'rm -rf "$SCRATCH"' EXIT

if [[ -t 1 ]]; then
    G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; N=$'\033[0m'
else
    G=""; R=""; Y=""; B=""; N=""
fi

PASS=0
FAIL=0
FAILURES=()

step() { printf "\n${B}== %s ==${N}\n" "$*"; }
ok()   { printf "  ${G}PASS${N}: %s\n" "$*"; PASS=$((PASS + 1)); }
bad()  { printf "  ${R}FAIL${N}: %s\n" "$*"; FAIL=$((FAIL + 1)); FAILURES+=("$*"); }
warn() { printf "  ${Y}SKIP${N}: %s\n" "$*"; }

# Real-world lock files at pinned refs.
# Format: label|source|filename
#   source = http(s) URL  -> curl downloads it
#   source = local:<path> -> copies from this repo
# Pinned refs are tags or specific commits so the test is reproducible. Bump
# them periodically when upstream releases newer versions to keep the smoke
# pointed at current real-world data.
PROJECTS=(
    "license-audit (self)|local:uv.lock|uv.lock"
    "pydantic-ai 0.0.20|https://raw.githubusercontent.com/pydantic/pydantic-ai/v0.0.20/uv.lock|uv.lock"
    "poetry 2.1.4|https://raw.githubusercontent.com/python-poetry/poetry/2.1.4/poetry.lock|poetry.lock"
    "pixi pypi example v0.50.0|https://raw.githubusercontent.com/prefix-dev/pixi/v0.50.0/examples/pypi/pixi.lock|pixi.lock"
    "requests v2.32.3|https://raw.githubusercontent.com/psf/requests/v2.32.3/requirements-dev.txt|requirements.txt"
)

# -----------------------------------------------------------------------------
# Per-project test: parse + analyze a real lock file end-to-end.
# -----------------------------------------------------------------------------

run_project() {
    local label=$1 source=$2 filename=$3
    local slug=${label// /-}
    slug=${slug//(/}; slug=${slug//)/}
    local dir="$SCRATCH/$slug"
    mkdir -p "$dir"

    # Step 1: stage the lock file.
    if [[ "$source" == local:* ]]; then
        cp "$REPO/${source#local:}" "$dir/$filename" 2>/dev/null || {
            bad "$label: local file ${source#local:} not found in repo"
            return
        }
    else
        if ! curl -fsSL --max-time 30 "$source" -o "$dir/$filename"; then
            warn "$label: download failed (network/upstream issue)"
            return
        fi
    fi

    # Step 2: run analyze --format json against the real lock file.
    local out="$dir/out.json"
    local err="$dir/err"
    set +e
    uv run license-audit --target "$dir/$filename" analyze --format json \
        >"$out" 2>"$err"
    local rc=$?
    set -e

    if (( rc != 0 )); then
        bad "$label: license-audit exited $rc (stderr: $(head -c 200 "$err"))"
        return
    fi

    # Step 3: parse the JSON output and validate shape.
    local count
    count=$(uv run --quiet python <<EOF
import json, sys
try:
    d = json.load(open("$out"))
except Exception as e:
    print(f"INVALID:{e}")
    sys.exit(0)
if "packages" not in d:
    print("MISSING_PACKAGES")
    sys.exit(0)
print(len(d["packages"]))
EOF
)

    case "$count" in
        INVALID:*)         bad "$label: JSON output not parseable (${count#INVALID:})" ;;
        MISSING_PACKAGES)  bad "$label: JSON output missing 'packages' key" ;;
        0)                 bad "$label: JSON output has zero packages" ;;
        *[!0-9]*)          bad "$label: unexpected python output: $count" ;;
        *)                 ok "$label: analyzed $count packages" ;;
    esac
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

step "Real-world projects (network required)"
echo "  Scratch: $SCRATCH"

for entry in "${PROJECTS[@]}"; do
    IFS='|' read -r label source filename <<< "$entry"
    run_project "$label" "$source" "$filename"
done

step "Summary"
TOTAL=$((PASS + FAIL))
printf "  Total: %d  ${G}Pass: %d${N}  ${R}Fail: %d${N}\n" "$TOTAL" "$PASS" "$FAIL"

if (( FAIL > 0 )); then
    printf "\n${R}Failures:${N}\n"
    for f in "${FAILURES[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
