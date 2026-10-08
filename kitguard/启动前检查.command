#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
  printf '%s\n' '실행 환경이 없습니다 / 缺少运行环境，请先运行 bash scripts/setup.sh'
  exit 1
fi
printf '%s\n' '실행 중인 서버를 읽기 전용으로 확인합니다 / 只读检查正在运行的服务。'
if .venv/bin/python scripts/preflight.py --port "${KITGUARD_PORT:-8765}" --mode "${KITGUARD_READINESS_MODE:-main}"; then
  result=0
else
  result=$?
fi
printf '%s\n' "화면 / 页面：http://127.0.0.1:${KITGUARD_PORT:-8765}/static/readiness.html"
if [[ -t 0 ]]; then
  read -r -p 'Enter 키로 닫기 / 按回车关闭 ' _readiness_close
fi
exit "$result"
