#!/usr/bin/env bash
# Restore the encrypted, multipart AI·SW backup into an empty directory.
set -euo pipefail

fail() { printf '错误：%s\n' "$*" >&2; exit 1; }

if [[ $# -ne 3 ]]; then
  printf '用法：%s <分卷及校验文件目录> <私钥路径> <空的恢复目录>\n' "$0" >&2
  exit 2
fi

parts_dir=$1
key_path=$2
destination=$3

for dependency in age zstd tar python3; do
  command -v "$dependency" >/dev/null 2>&1 || fail "缺少依赖：$dependency"
done
if command -v sha256sum >/dev/null 2>&1; then
  checksum_command=(sha256sum -c SHA256SUMS.txt)
elif command -v shasum >/dev/null 2>&1; then
  checksum_command=(shasum -a 256 -c SHA256SUMS.txt)
else
  fail '缺少 SHA-256 校验工具：需要 sha256sum 或 shasum'
fi

[[ -d "$parts_dir" ]] || fail '分卷目录不存在'
[[ -f "$key_path" ]] || fail '私钥文件不存在'
[[ -n "$destination" ]] || fail '恢复目录路径不能为空'
[[ ! -L "$destination" ]] || fail '恢复目录不能是符号链接'

# Make paths absolute before changing into the download directory.
parts_dir=$(cd -- "$parts_dir" && pwd -P)
key_path=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$key_path")
destination=$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$destination")
[[ -f "$parts_dir/SHA256SUMS.txt" ]] || fail '缺少 SHA256SUMS.txt'

# Reject empty or unsafe checksum lists before using a checksum utility.
python3 - "$parts_dir/SHA256SUMS.txt" <<'PY'
import re
import sys
from pathlib import PurePosixPath

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
if not lines:
    raise SystemExit("错误：SHA256SUMS.txt 为空")
seen = set()
for line in lines:
    match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
    if not match:
        raise SystemExit("错误：SHA256SUMS.txt 格式不受支持")
    name = match[2]
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or name in seen:
        raise SystemExit("错误：SHA256SUMS.txt 包含不安全或重复路径")
    if "RESTORE-KEY" in name or name.endswith(".agekey"):
        raise SystemExit("错误：校验清单不能包含私钥")
    seen.add(name)
PY

printf '正在校验全部备份附件……\n'
(cd -- "$parts_dir" && "${checksum_command[@]}")

shopt -s nullglob
parts=("$parts_dir"/AI-SW-full-20261008.tar.zst.age.part-*)
[[ ${#parts[@]} -gt 0 ]] || fail '未找到备份分卷'
expected=1
for part in "${parts[@]}"; do
  printf -v expected_name 'AI-SW-full-20261008.tar.zst.age.part-%06d' "$expected"
  [[ "${part##*/}" == "$expected_name" ]] || fail "分卷序号不连续，预期：$expected_name"
  [[ -f "$part" && ! -L "$part" ]] || fail "分卷不是普通文件：${part##*/}"
  # Every consumed part must have an authenticated checksum entry.
  python3 - "$parts_dir/SHA256SUMS.txt" "$expected_name" <<'PY'
import sys
names = {line.rstrip("\n")[66:] for line in open(sys.argv[1], encoding="utf-8")}
if sys.argv[2] not in names:
    raise SystemExit("错误：分卷未列入 SHA256SUMS.txt：" + sys.argv[2])
PY
  expected=$((expected + 1))
done

mkdir -p -- "$destination"
[[ -d "$destination" && ! -L "$destination" ]] || fail '恢复目标必须是普通目录'
python3 - "$destination" <<'PY'
import os
import sys
with os.scandir(sys.argv[1]) as entries:
    if next(entries, None) is not None:
        raise SystemExit("错误：恢复目录必须为空，脚本不会覆盖现有文件")
PY

printf '正在解密、解压并恢复到：%s\n' "$destination"
cat -- "${parts[@]}" | age --decrypt -i "$key_path" | zstd -d -c | tar -x -f - -C "$destination"
printf '解压完成。请运行 verify-restored.py 校验恢复文件。\n'
