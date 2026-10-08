"""Read-only local readiness report; no inference, downloads or model loading."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kitguard import __version__
from kitguard.readiness import build_readiness_report


def fetch_json(url):
    with urlopen(url, timeout=8) as response:
        document = json.load(response)
    if not isinstance(document, dict):
        raise TypeError("Expected an object response")
    return document


def collect_report(port, mode):
    base = f"http://127.0.0.1:{port}"
    try:
        report = fetch_json(f"{base}/api/readiness?mode={mode}")
        if report.get("schema") != "kitguard.readiness.v1" or report.get("mode") != mode:
            raise ValueError("Unsupported readiness report")
        if (not isinstance(report.get("checks"), list) or not isinstance(report.get("scopes"), dict)
                or type(report.get("ready")) is not bool
                or any(not isinstance(scope, dict) for scope in report["scopes"].values())):
            raise TypeError("Invalid readiness report")
        if report.get("version") != __version__:
            report["ready"] = False
            for scope in report["scopes"].values():
                if scope.get("checked"):
                    scope["ready"] = False
            report["checks"].append({
                "check": "client_server_version", "scope": "common", "passed": False,
                "required": True, "state": "fail", "label": {"ko": "실행 버전", "zh": "运行版本"},
                "message": {"ko": "이 프로젝트와 서버 버전이 다릅니다.", "zh": "当前项目与服务版本不同。"},
                "action": {"ko": "이 프로젝트의 서버를 다시 시작하세요.", "zh": "请重启当前项目的服务。"},
                "detail": {"expected": __version__, "running": report.get("version")},
            })
        report["client_version"] = __version__
        return report
    except (URLError, OSError, ValueError, KeyError, TypeError) as exc:
        error = type(exc).__name__
    # Legacy health can diagnose an older service, but cannot pass current readiness.
    try:
        health = fetch_json(f"{base}/api/health")
    except (URLError, OSError, ValueError, TypeError):
        health = {}
    detector = {}
    if mode in {"detector", "all"}:
        try:
            detector = fetch_json(f"{base}/api/detector-lab/status")
        except (URLError, OSError, ValueError, TypeError):
            pass
    report = build_readiness_report(
        package=ROOT / "kitguard", data_dir=Path(os.environ.get("KITGUARD_DATA_DIR", ROOT / "data")),
        health=health, detector=detector, mode=mode, server_error=error,
    )
    report["checks"].append({
        "check": "readiness_endpoint", "scope": "common", "passed": False, "required": True,
        "state": "fail", "label": {"ko": "점검 API", "zh": "检查接口"},
        "message": {"ko": "새 점검 API에 연결하지 못했습니다.", "zh": "未能连接当前版本的检查接口。"},
        "action": {"ko": f"현재 프로젝트의 서버를 시작하고 {port} 포트를 확인하세요.",
                   "zh": f"请启动当前项目的服务，并确认端口 {port}。"},
        "detail": {"error": error, "fallback": "local files and legacy health only"},
    })
    report["ready"] = False
    for scope in report["scopes"].values():
        if scope["checked"]:
            scope["ready"] = False
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--mode", choices=("main", "detector", "all"), default="main")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Invalid local port")
    if args.output and (args.output.exists() or args.output.is_symlink()):
        parser.error("Keep previous records; choose a new output file")
    report = collect_report(args.port, args.mode)
    content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(content)
        except OSError as exc:
            parser.error(f"Cannot create report without overwriting: {type(exc).__name__}")
    print(content)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
