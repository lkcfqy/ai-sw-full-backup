#!/usr/bin/env python3
"""Verify restored backup files without following unexpected symlinks."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


def safe_relative_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError("path 必须是非空字符串")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "\x00" in value:
        raise ValueError("清单路径不是安全的相对路径")
    if relative.parts[0] != "AI·SW":
        raise ValueError("清单路径必须以 AI·SW 为根目录")
    return relative


def checked_path(root, relative):
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("父目录含意外符号链接")
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("父路径不是目录")
    return current / relative.parts[-1]


def verify_row(root, row):
    relative = safe_relative_path(row.get("path"))
    target = checked_path(root, relative)
    metadata = os.lstat(target)
    kind = row.get("type", "file")
    if kind in {"file", "regular", "regular_file"}:
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("目标不是普通文件，或已变为符号链接")
        expected_size = row.get("size")
        if type(expected_size) is not int or expected_size < 0:
            raise ValueError("清单 size 无效")
        if metadata.st_size != expected_size:
            raise ValueError(f"大小不一致：{metadata.st_size}，预期 {expected_size}")
        expected_hash = row.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            raise ValueError("清单 sha256 无效")
        # O_NOFOLLOW rejects a symlink introduced between lstat and open.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError("打开的目标不是普通文件")
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise ValueError("校验期间文件发生替换")
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_hash.lower():
            raise ValueError("SHA-256 不一致")
    elif kind in {"symlink", "link"}:
        if not stat.S_ISLNK(metadata.st_mode):
            raise ValueError("目标不是符号链接")
        expected_target = row.get("target")
        if not isinstance(expected_target, str) or os.readlink(target) != expected_target:
            raise ValueError("符号链接指向不一致")
    elif kind in {"directory", "dir"}:
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("目标不是普通目录")
    else:
        raise ValueError(f"不支持的清单类型：{kind!r}")
    return relative.as_posix(), kind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="file-manifest.jsonl 路径")
    parser.add_argument("destination", type=Path, help="包含 AI·SW 的恢复目录")
    arguments = parser.parse_args()
    if arguments.destination.is_symlink() or not arguments.destination.is_dir():
        parser.error("恢复目录不存在、不是目录或是符号链接")
    root = arguments.destination.resolve()
    seen = set()
    verified = 0
    failed = 0
    try:
        with arguments.manifest.open(encoding="utf-8") as manifest:
            for line_number, line in enumerate(manifest, 1):
                if not line.strip():
                    continue
                row = None
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("清单条目必须是 JSON 对象")
                    relative = safe_relative_path(row.get("path")).as_posix()
                    if relative in seen:
                        raise ValueError("清单路径重复")
                    seen.add(relative)
                    verify_row(root, row)
                    verified += 1
                except (OSError, ValueError, TypeError) as error:
                    failed += 1
                    if failed <= 100:
                        label = row.get("path") if isinstance(row, dict) else None
                        print(f"失败：第 {line_number} 行，{label!r}：{error}", file=sys.stderr)
    except (OSError, UnicodeError) as error:
        print(f"读取清单失败：{error}", file=sys.stderr)
        return 1
    if verified + failed == 0:
        print("失败：清单没有条目", file=sys.stderr)
        return 1
    print(f"校验完成：通过 {verified} 项，失败 {failed} 项。")
    if failed > 100:
        print(f"另有 {failed - 100} 项失败，已省略逐项输出。", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
