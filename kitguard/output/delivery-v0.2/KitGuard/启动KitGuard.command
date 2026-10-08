#!/bin/bash
cd -- "$(dirname -- "$0")"
printf '%s\n' 'KitGuard 本地工作台：http://127.0.0.1:8765' '关闭本窗口或按 Ctrl+C 停止服务。'
exec bash scripts/run.sh
