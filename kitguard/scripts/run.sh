#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if [[ ! -x .venv/bin/python ]]; then
  printf '%s\n' '尚未安装运行环境，请先运行：bash scripts/setup.sh'
  exit 1
fi
export KITGUARD_MODEL_PATH="${KITGUARD_MODEL_PATH:-$project_dir/models/Qwen3.6-27B-4bit}"
export KITGUARD_OBSERVATION_MODE="${KITGUARD_OBSERVATION_MODE:-spatial_guarded}"
export KITGUARD_IMAGE_MAX_SIDE="${KITGUARD_IMAGE_MAX_SIDE:-1536}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
exec .venv/bin/python -m uvicorn kitguard.app:app --host 127.0.0.1 --port "${KITGUARD_PORT:-8765}" --workers 1
