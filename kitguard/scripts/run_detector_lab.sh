#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
export KITGUARD_DETECTOR_CHECKPOINT="${KITGUARD_DETECTOR_CHECKPOINT:-$project_dir/training-runs/public_detector_v1_mps_20260930/best.pt}"
export KITGUARD_DATA_DIR="${KITGUARD_DATA_DIR:-$project_dir/data-detector-lab}"
export KITGUARD_PORT="${KITGUARD_PORT:-8767}"
if [[ ! -f "$KITGUARD_DETECTOR_CHECKPOINT" ]]; then
  printf '%s\n' '检测权重尚未准备好。请查看 docs/training/PUBLIC_DETECTOR_V1.md。'
  exit 1
fi
printf '%s\n' "KitGuard 检测验证台：http://127.0.0.1:$KITGUARD_PORT/static/detector.html" 'CPU独立运行；关闭窗口或按 Ctrl+C 停止。'
exec bash scripts/run.sh
