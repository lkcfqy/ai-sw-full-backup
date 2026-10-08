#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  printf '%s\n' '此本地推理环境面向 Apple Silicon Mac；其他设备需要单独适配推理后端。'
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' '请先安装 uv：https://docs.astral.sh/uv/getting-started/installation/'
  exit 1
fi
if [[ ! -f requirements-lock.txt ]]; then
  printf '%s\n' '缺少 requirements-lock.txt，请使用完整项目目录。'
  exit 1
fi
uv venv --python 3.12 --allow-existing .venv
uv pip install --python .venv/bin/python -r requirements-lock.txt
uv pip install --python .venv/bin/python --no-deps -e .
printf '%s\n' '环境就绪。模型未下载时运行：.venv/bin/python scripts/download_candidate_model.py' '启动：bash scripts/run.sh'
