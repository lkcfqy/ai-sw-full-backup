#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export KITGUARD_DATA_DIR="${KITGUARD_DATA_DIR:-$project_dir/data-competition-v09}"
exec bash "$project_dir/scripts/run.sh"
