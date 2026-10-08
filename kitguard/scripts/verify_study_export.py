"""Independently verify closed schema-1 study JSON; no app imports or model calls.

This checks internal consistency, not signatures, image bytes, physical reality,
complete capture of events outside this document, or independently measured time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

PARTS = {"bolt", "nut", "washer", "bracket"}
METHODS = ("manual", "kitguard")
IDENTITY = ("repo_id", "revision", "observer_protocol_sha256", "observation_mode", "image_max_side")
STATES = ("correct", "wrong", "uncertain", "failed", "abandoned", "interrupted", "not_started")
LIMITS = [
    "Internal consistency only; an entirely rewritten unsigned document cannot be authenticated.",
    "No image bytes are provided, so stored image digests are checked as bindings, not recomputed.",
    "Elapsed milliseconds are checked and summarized, not independently remeasured.",
    "Self-reported sources, independent counting, and physical reality are not verified.",
    "Checks/events omitted consistently from all document sections cannot be detected without an external log.",
]


class InvalidExport(ValueError):
    pass


def require(value, message):
    if not value:
        raise InvalidExport(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def hexadecimal(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value), f"{label}: invalid SHA/nonce")


def integer(value, low, high, label):
    require(type(value) is int and low <= value <= high, f"{label}: strict integer out of range")


def counts(value, label, *, unknown=False, requirements=False):
    require(isinstance(value, dict) and set(value) == PARTS, f"{label}: four categories required")
    for part, number in value.items():
        if number is None and unknown:
            continue
        integer(number, 0, 3 if requirements else 100, f"{label}.{part}")
    if requirements:
        require(1 <= sum(value.values()) <= 12, f"{label}: invalid order total")


def timestamp(value, label):
    require(isinstance(value, str), f"{label}: timestamp required")
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, f"{label}: timezone required")
    return result


def validate_scope(record, label, *, required=False, before=None):
    """Check the declared coordinate contract, without authenticating picture content."""
    scope = record.get("inspection_scope")
    if scope is None:
        require(not required, f"{label}: required inspection scope missing")
        return None
    require(isinstance(scope, dict), f"{label}: inspection scope must be an object")
    keys = {"mode", "view_photo_id", "view_sha256", "root_photo_id", "root_photo_sha256",
            "source_family_sha256", "root_width", "root_height", "root_source_sha256",
            "root_created_at", "region_xyxy", "coordinate_space", "derivation",
            "scope_declaration", "scope_confirmed_at"}
    require(set(scope) == keys, f"{label}: unsupported scope fields")
    require(scope["mode"] in ("whole_image", "region"), f"{label}: invalid scope mode")
    require(isinstance(scope["view_photo_id"], str) and bool(scope["view_photo_id"]), f"{label}: view ID missing")
    require(scope["view_photo_id"] == record["photo_id"] and scope["view_sha256"] == record["photo_sha256"],
            f"{label}: view identity differs from record")
    require(isinstance(scope["root_photo_id"], str) and bool(scope["root_photo_id"]), f"{label}: root ID missing")
    for key in ("view_sha256", "root_photo_sha256", "source_family_sha256"):
        hexadecimal(scope[key], f"{label}.{key}")
    require(record.get("source_family_sha256") == scope["source_family_sha256"] == scope["root_photo_sha256"],
            f"{label}: source family differs from root")
    require(scope["coordinate_space"] == "normalized_root_pixels_xyxy_half_open_v1",
            f"{label}: unsupported coordinate space")
    for key in ("root_width", "root_height"):
        integer(scope[key], 32, 8192, f"{label}.{key}")
    if scope["root_source_sha256"] is not None:
        hexadecimal(scope["root_source_sha256"], f"{label}.root_source_sha256")
    root_time = timestamp(scope["root_created_at"], f"{label}.root_created_at") if scope["root_created_at"] is not None else None
    if root_time is not None and before is not None:
        require(root_time <= before, f"{label}: root created after bound record")
    derived = scope["root_photo_id"] != scope["view_photo_id"]
    if scope["mode"] == "region":
        require(derived, f"{label}: crop cannot be its own root")
        rect = scope["region_xyxy"]
        require(isinstance(rect, list) and len(rect) == 4, f"{label}: four region boundaries required")
        for value in rect:
            integer(value, 0, 8192, f"{label}.region_xyxy")
        left, top, right, bottom = rect
        require(0 <= left < right <= scope["root_width"] and 0 <= top < bottom <= scope["root_height"]
                and right-left >= 32 and bottom-top >= 32, f"{label}: invalid region geometry")
        require(scope["derivation"] == "pillow_root_crop_rgb_jpeg95_v1", f"{label}: crop encoding mismatch")
    else:
        require(scope["region_xyxy"] is None and scope["view_sha256"] == scope["root_photo_sha256"],
                f"{label}: whole-image must use exact root bytes")
        require(scope["derivation"] == "normalized_root_bytes_v1", f"{label}: whole-image derivation mismatch")
    if derived:
        require(scope["scope_declaration"] == "operator_all_required_items_inside", f"{label}: scope declaration missing")
        confirmed = timestamp(scope["scope_confirmed_at"], f"{label}.scope_confirmed_at")
        require(root_time is None or root_time <= confirmed, f"{label}: confirmation predates stored root")
        require(before is None or confirmed <= before, f"{label}: confirmation after bound record")
    else:
        require(scope["scope_declaration"] is None and scope["scope_confirmed_at"] is None,
                f"{label}: untouched root has a fabricated selection declaration")
    return scope


def timing(values):
    ordered = sorted(v for v in values if v is not None)
    n = len(ordered)
    median = None if not n else ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    return {"n": n, "median": median, "max": ordered[-1] if n else None}


def category(check, truth):
    if check["decision"] in ("manual", "recapture") or any(v is None for v in check["observed"].values()):
        return "uncertain"
    return "correct" if check["observed"] == truth else "wrong"


def same_metrics(actual, expected, path=()):
    """JSON clients may write a numeric ratio 1.0 as 1; counts stay strict integers."""
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(same_metrics(actual[key], value, (*path, key)) for key, value in expected.items()))
    if path and path[-1] in {"correct_fraction", "median"} and type(expected) in (int, float):
        return type(actual) in (int, float) and actual == expected
    return type(actual) is type(expected) and actual == expected


def matching_identity(check, study):
    return all(check["runtime_identity"].get(k) == study["runtime_identity"].get(k) for k in IDENTITY)


def validate_check(check, case, start, finish):
    require(isinstance(check, dict), "check must be an object")
    require(check["order_id"] == case["order_id"], "check belongs to another order")
    counts(check["observed"], "check.observed", unknown=True)
    counts(check["requirements_snapshot"], "check.requirements_snapshot", requirements=True)
    hexadecimal(check["photo_sha256"], "check.photo_sha256")
    validate_scope(check, "check.scope", required=case.get("inspection_scope") is not None,
                   before=timestamp(check["created_at"], "check.created_at"))
    require(start <= timestamp(check["created_at"], "check.created_at") <= finish,
            "check timestamp outside trial window")
    require(check["decision"] in ("ready", "correct", "manual", "recapture"), "unsupported check decision")
    require(check["backend"] in ("test", "mlx"), "unsupported check backend")
    require(isinstance(check["runtime_identity"], dict), "missing check runtime identity")
    require(type(check["valid"]) is bool, "check.valid must be boolean")
    integer(check["revision"], 1, 2**31, "check.revision")
    integer(check["evidence_epoch"], 0, 2**31, "check.evidence_epoch")
    integer(check["latency_ms"], 0, 2**63 - 1, "check.latency_ms")
    require(isinstance(check["issues"], list), "check.issues must be a list")
    if check["decision"] in ("ready", "correct"):
        require(all(v is not None for v in check["observed"].values()) and not check["issues"],
                "clear decision contains uncertainty")
        equal = check["observed"] == check["requirements_snapshot"]
        require(equal == (check["decision"] == "ready"), "decision contradicts observed/order counts")
        require(check["action"]["kind"] == ("none" if equal else "add_remove"), "clear decision/action mismatch")


def validate_trial(trial, method, case, study, used_ids):
    require(trial["id"] not in used_ids, "duplicate trial ID")
    used_ids.add(trial["id"])
    require(trial["method"] == method, "trial method mismatch")
    require(trial["status"] in ("completed", "failed", "abandoned", "interrupted"), "closed export has nonterminal trial")
    require(all(trial[key] == case[key] for key in ("order_id", "photo_id", "revision")), "trial/case binding mismatch")
    require(not any(k in trial for k in ("_monotonic_started", "_process_nonce")), "private timing state leaked")
    start = timestamp(trial["started_at"], "trial.started_at")
    finish = timestamp(trial["finished_at"], "trial.finished_at")
    require(timestamp(study["frozen_at"], "frozen_at") <= start <= finish <= timestamp(study["closed_at"], "closed_at"),
            "trial chronology violates freeze/closure")
    if trial["status"] == "interrupted":
        require(trial["elapsed_ms"] is None, "interrupted duration must remain unknown")
    else:
        integer(trial["elapsed_ms"], 0, 2**63 - 1, "trial.elapsed_ms")
    evidence = trial["evidence"]
    require(start <= timestamp(evidence["captured_at"], "evidence.captured_at") <= finish, "capture outside trial window")
    events, checks = evidence["events"], evidence["checks"]
    require(isinstance(events, list) and isinstance(checks, list), "evidence arrays required")
    event_times = [timestamp(e["created_at"], "evidence event") for e in events]
    require(event_times == sorted(event_times) and all(start <= t <= finish for t in event_times), "evidence event chronology invalid")
    starts = [e for e in events if e["kind"] == "inspection_started"]
    done = [e for e in events if e["kind"] == "inspection_completed"]
    check_ids = [c["id"] for c in checks]
    require(len(check_ids) == len(set(check_ids)), "duplicate returned check")
    require(sorted(check_ids) == sorted(e["payload"]["check_id"] for e in done), "completed events/checks differ: missing or extra return")
    require(len(starts) >= len(checks), "check returned without an inspection attempt")
    for check in checks:
        validate_check(check, case, start, finish)
        event = next(e for e in done if e["payload"]["check_id"] == check["id"])
        require(event["payload"]["decision"] == check["decision"] and event["payload"]["revision"] == check["revision"],
                "completed event contradicts check")
        require(any(e["payload"].get("photo_id") == check["photo_id"]
                    and timestamp(e["created_at"], "inspection start") <= timestamp(check["created_at"], "check time")
                    for e in starts), "check has no preceding attempt on the same photo")
    if trial["status"] == "completed":
        if method == "manual":
            counts(trial["manual_counts"], "manual_counts")
            require(trial["check"] is None and not starts and not checks, "completed manual trial contains AI exposure")
        else:
            require(trial["manual_counts"] is None and len(starts) == len(checks) == 1, "AI completion requires one attempt and one check")
            selected = trial["check"]
            require(selected == checks[0], "selected check differs from preserved return")
            require(selected["valid"] is True, "selected check invalid")
            bindings = {"photo_id": "photo_id", "photo_sha256": "photo_sha256", "revision": "revision",
                        "evidence_epoch": "evidence_epoch", "reference_ids": "reference_ids", "requirements_snapshot": "requirements"}
            require(all(selected[a] == case[b] for a, b in bindings.items()), "selected check/case binding mismatch")
            if case.get("inspection_scope") is not None:
                require(selected.get("inspection_scope") == case["inspection_scope"], "selected check/frozen scope mismatch")
                require(selected.get("source_family_sha256") == case["source_family_sha256"], "selected check/family mismatch")
            require(matching_identity(selected, study), "selected runtime differs from frozen runtime")
            require(study["source_kind"] == "engineering_fixture" or selected["backend"] == "mlx", "test backend promoted to real model")
    else:
        require(trial["check"] is None and trial["manual_counts"] is None, "noncompleted trial has substituted result")
        require(isinstance(trial["note"], str) and trial["note"].strip(), "noncompleted reason missing")
    if study["source_kind"] == "self_reported_physical" and trial["status"] == "completed":
        require(not evidence.get("other_order_exposures"), "physical completion contains known outside exposure")
    return start, finish


def recalculate(study):
    output = {}
    for method in METHODS:
        observed = [c["trials"][method] for c in study["cases"] if c["trials"][method] is not None]
        m = dict.fromkeys(STATES, 0)
        m.update({"planned": study["planned_cases"], "started": len(observed), "completed": 0})
        m["not_started"] = study["planned_cases"] - len(observed)
        returned = dict.fromkeys(("total", "scorable", "wrong_clear", "false_ready", "uncertain",
                                  "multiple_attempt_trials", "ineligible_backend_or_identity"), 0)
        false_ready = 0
        for case in study["cases"]:
            trial = case["trials"][method]
            if trial is None:
                continue
            if trial["status"] == "completed":
                m["completed"] += 1
                cat = ("correct" if trial["manual_counts"] == case["truth"] else "wrong") if method == "manual" else category(trial["check"], case["truth"])
                m[cat] += 1
                if method == "kitguard":
                    false_ready += int(trial["check"]["decision"] == "ready" and case["truth"] != case["requirements"])
            else:
                m[trial["status"]] += 1
            returned["multiple_attempt_trials"] += int(sum(e["kind"] == "inspection_started" for e in trial["evidence"]["events"]) > 1)
            for check in trial["evidence"]["checks"]:
                returned["total"] += 1
                if study["source_kind"] != "engineering_fixture" and (check["backend"] != "mlx" or not matching_identity(check, study)):
                    returned["ineligible_backend_or_identity"] += 1
                    continue
                if check["photo_sha256"] != case["photo_sha256"] or check["revision"] != case["revision"] or check["requirements_snapshot"] != case["requirements"]:
                    continue
                returned["scorable"] += 1
                returned["wrong_clear"] += int(category(check, case["truth"]) == "wrong")
                returned["uncertain"] += int(category(check, case["truth"]) == "uncertain")
                returned["false_ready"] += int(check["decision"] == "ready" and case["truth"] != case["requirements"])
        m["correct_fraction"] = m["correct"] / m["planned"] if observed else None
        m["terminal_elapsed_ms"] = timing([t["elapsed_ms"] for t in observed])
        m["completed_elapsed_ms"] = timing([t["elapsed_ms"] for t in observed if t["status"] == "completed"])
        m["false_ready"] = {"numerator": false_ready, "denominator": sum(c["truth"] != c["requirements"] for c in study["cases"])} if method == "kitguard" else None
        m["returned_checks"] = returned
        require(sum(m[k] for k in STATES) == study["planned_cases"], "recomputed denominator failed conservation")
        output[method] = m
    return output


def validate(payload):
    require(type(payload["schema_version"]) is int and payload["schema_version"] == 1, "only schema_version 1 supported")
    require(payload["kind"] == "kitguard_fixed_state_study", "unsupported export kind")
    study = payload["study"]
    require(study["status"] == "closed", "only closed studies can be verified")
    require(study["source_kind"] in ("engineering_fixture", "public_replay", "self_reported_physical"), "unsupported source kind")
    integer(study["planned_cases"], 1, 48, "planned_cases")
    require(isinstance(study["cases"], list) and len(study["cases"]) <= study["planned_cases"], "case count exceeds planned denominator")
    created, closed = timestamp(study["created_at"], "created_at"), timestamp(study["closed_at"], "closed_at")
    require(created <= closed, "closure before creation")
    frozen = study["frozen_at"]
    if frozen is not None:
        require(created <= timestamp(frozen, "frozen_at") <= closed, "freeze chronology invalid")
        require(len(study["cases"]) == study["planned_cases"], "frozen study missing registered cases")
        hexadecimal(study["recorder_source_sha256"], "recorder_source_sha256")
        require(study["protocol_sha256"] == digest(study["protocol"]), "protocol digest mismatch")
        require(isinstance(study["runtime_identity"], dict), "frozen runtime missing")
    else:
        require(study["protocol_sha256"] is None and study["runtime_identity"] is None, "unfrozen study has frozen identity")
    require(study["protocol"]["name"] == "fixed_state_manual_then_kitguard_v1" and study["protocol"]["methods"] == list(METHODS), "unsupported protocol")
    scope_policy = study["protocol"].get("inspection_scope_policy")
    require(scope_policy in (None, "operator_region_v1"), "unsupported inspection scope policy")
    identities = {k: set() for k in ("id", "order_id", "photo_sha256")}
    family_aliases = set()
    used_trials, windows = set(), []
    for case in study["cases"]:
        for key, seen in identities.items():
            require(case[key] not in seen, f"duplicate case {key}")
            seen.add(case[key])
        hexadecimal(case["photo_sha256"], "photo_sha256")
        hexadecimal(case["truth_nonce"], "truth_nonce")
        counts(case["truth"], "truth")
        counts(case["requirements"], "requirements", requirements=True)
        require(case["truth_commitment"] == digest({"truth": case["truth"], "nonce": case["truth_nonce"]}), "truth commitment mismatch")
        require(case["confirmed_independent"] is True, "independence declaration missing")
        integer(case["revision"], 1, 2**31, "case.revision")
        integer(case["evidence_epoch"], 0, 2**31, "case.evidence_epoch")
        registered = timestamp(case["registered_at"], "registered_at")
        scope = validate_scope(case, "case.scope", required=scope_policy is not None, before=registered)
        if scope is not None:
            aliases = {value for value in (scope["root_photo_sha256"], scope["root_source_sha256"], scope["view_sha256"]) if value}
            require(not aliases.intersection(family_aliases), "cases share a known photo family or exact byte alias")
            family_aliases.update(aliases)
        require(created <= registered <= (timestamp(frozen, "frozen_at") if frozen else closed), "registration chronology invalid")
        require(set(case["reference_ids"]) == set(case["reference_sha256"]) <= PARTS, "reference binding categories mismatch")
        for value in case["reference_sha256"].values():
            hexadecimal(value, "reference_sha256")
        require(not case["demo_source"] or study["source_kind"] == "public_replay", "known public source promoted")
        require(set(case["trials"]) == set(METHODS), "method slots incomplete")
        for method in METHODS:
            trial = case["trials"][method]
            if trial is None:
                continue
            require(frozen is not None, "trial began without freeze")
            start, finish = validate_trial(trial, method, case, study, used_trials)
            windows.append((start, finish, trial["id"]))
            if method == "kitguard":
                manual = case["trials"]["manual"]
                require(manual is not None and timestamp(manual["finished_at"], "manual.finished_at") <= start,
                        "AI started before manual finished")
    ordered = sorted(windows)
    require(all(a[1] <= b[0] for a, b in pairwise(ordered)), "overlapping trials in one study")
    study_events = study["events"]
    event_times = [timestamp(e["created_at"], "study event") for e in study_events]
    require(event_times == sorted(event_times) and all(created <= t <= closed for t in event_times), "study event chronology invalid")
    require(sum(e["kind"] == "closed" for e in study_events) == 1, "single closure event required")
    require(next(timestamp(e["created_at"], "closure event") for e in study_events if e["kind"] == "closed") == closed,
            "closure event timestamp mismatch")
    freeze_events = [e for e in study_events if e["kind"] == "frozen"]
    require(len(freeze_events) == int(frozen is not None), "freeze event count mismatch")
    if frozen:
        require(timestamp(freeze_events[0]["created_at"], "freeze event") >= timestamp(frozen, "frozen_at"), "freeze event precedes freeze")
    starts = [e["payload"]["trial_id"] for e in study_events if e["kind"] == "trial_started"]
    require(len(starts) == len(set(starts)) and set(starts) == used_trials, "trial start log/slots differ")
    registrations = [e["payload"] for e in study_events if e["kind"] == "case_registered"]
    require(len(registrations) == len(study["cases"]), "registration event count mismatch")
    for case in study["cases"]:
        require(sum(e.get("case_id") == case["id"] and e.get("truth_commitment") == case["truth_commitment"] for e in registrations) == 1,
                "registered commitment differs from case")
        for method, trial in case["trials"].items():
            if trial is None:
                continue
            start_event = next(e for e in study_events if e["kind"] == "trial_started" and e["payload"]["trial_id"] == trial["id"])
            require(start_event["payload"]["case_id"] == case["id"] and start_event["payload"]["method"] == method,
                    "trial start event belongs to a different case/method")
            require(timestamp(trial["started_at"], "trial start") <= timestamp(start_event["created_at"], "start event") <= timestamp(trial["finished_at"], "trial finish"),
                    "trial start event outside trial window")
            end_events = [e for e in study_events if e["kind"] in ("trial_finished", "trial_interrupted") and e["payload"].get("trial_id") == trial["id"]]
            require(len(end_events) <= 1, "duplicate trial termination events")
            if end_events:
                event = end_events[0]
                status = "interrupted" if event["kind"] == "trial_interrupted" else event["payload"]["status"]
                require(status == trial["status"], "terminal event/status mismatch")
                require(timestamp(event["created_at"], "terminal event") >= timestamp(trial["finished_at"], "trial finish"), "terminal event precedes finish")
            else:
                require(trial["status"] in ("abandoned", "interrupted") and timestamp(trial["finished_at"], "trial finish") <= closed,
                        "terminal trial lacks a completion/recovery/closure event")
    methods = recalculate(study)
    report = study["report"]
    require(same_metrics(report["methods"], methods), "reported method metrics differ from independent recomputation")
    require(report["scope"] == study["protocol"]["name"] and report["source_kind"] == study["source_kind"], "report identity mismatch")
    require(type(report["planned_cases"]) is int and report["planned_cases"] == study["planned_cases"], "reported planned denominator mismatch")
    require(type(report["registered_cases"]) is int and report["registered_cases"] == len(study["cases"]), "reported registered denominator mismatch")
    paired = sum(all(c["trials"][m] and c["trials"][m]["status"] == "completed" for m in METHODS) for c in study["cases"])
    require(type(report["paired_completed_cases"]) is int and report["paired_completed_cases"] == paired, "paired completion mismatch")
    return {"study_id": study["id"], "source_kind": study["source_kind"], "planned_cases": study["planned_cases"],
            "registered_cases": len(study["cases"]), "checked_trials": len(used_trials), "recomputed_methods": methods}


def verify_payload(payload):
    receipt = {"schema_version": 1, "verifier": "independent_study_export_v1", "status": "invalid",
               "verified_at": datetime.now(UTC).isoformat(), "errors": [], "limitations": LIMITS,
               "physical_authenticity_verified": False, "photo_bytes_verified": False, "signature_verified": False}
    try:
        receipt.update(validate(payload))
        receipt["status"] = "verified_internal_consistency"
    except (InvalidExport, KeyError, TypeError, ValueError, AttributeError) as exc:
        receipt["errors"].append(f"{type(exc).__name__}: {exc}")
    return receipt


def parse_json(content):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def finite(value):
        raise InvalidExport(f"nonfinite JSON constant: {value}")

    return json.loads(content, object_pairs_hook=unique, parse_constant=finite)


def read_json(path):
    return parse_json(path.read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, help="Optional receipt path; refuses to overwrite an existing file")
    args = parser.parse_args(argv)
    try:
        raw = args.input.read_bytes()
        payload = parse_json(raw)
        receipt = verify_payload(payload)
        receipt["input_sha256"] = hashlib.sha256(raw).hexdigest()
        receipt["verifier_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        receipt = {"schema_version": 1, "verifier": "independent_study_export_v1", "status": "invalid",
                   "errors": [f"{type(exc).__name__}: {exc}"], "limitations": LIMITS}
    result = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(result)
        except OSError as exc:
            print(json.dumps({"status": "receipt_write_failed", "error": str(exc)}), file=sys.stderr)
            return 2
    print(result, end="")
    return 0 if receipt["status"] == "verified_internal_consistency" else 1


if __name__ == "__main__":
    raise SystemExit(main())
