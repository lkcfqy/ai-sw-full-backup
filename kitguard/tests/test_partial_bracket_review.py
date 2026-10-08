"""Independent runner counterexamples using only synthetic inputs and CPU stubs."""

import json

import pytest
from test_partial_bracket_benchmark import cpu_engine, execute, predictions, runner
from test_partial_bracket_benchmark import plan as plan  # noqa: PLC0414 -- pytest fixture re-export


def test_interrupt_after_first_source_keeps_original_planned_denominator(plan, monkeypatch):
    engine, _ = cpu_engine(monkeypatch)
    observe = engine.observe
    calls = 0

    def interrupt(path, requirements, references):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("Independent CPU interruption fixture")
        return observe(path, requirements, references)

    monkeypatch.setattr(engine, "observe", interrupt)
    with pytest.raises(KeyboardInterrupt):
        execute(plan, engine)
    metadata = runner.read_json(plan["output"] / "run.json")
    rows = predictions(plan)
    assert metadata["expected_cases"] == metadata["summary"]["planned_cases"] == 3
    assert len(rows) == 3
    assert metadata["summary"]["outcomes"] == {"C_b": 1, "W_b": 0, "U_b": 0, "E": 2}
    assert metadata["summary"]["author_bracket_count_agreement_fraction"] == pytest.approx(1 / 3)
    assert metadata["status"] != "completed"
    assert metadata["valid_frozen_run"] is False
    assert [r["elapsed_ms"] for r in rows[1:]] == [None, None]


def test_nonfinite_last_invalid_output_is_a_persisted_error_not_false_completion(plan, monkeypatch):
    engine, _ = cpu_engine(monkeypatch)
    observe = engine.observe
    calls = 0

    def malformed_last(path, requirements, references):
        nonlocal calls
        calls += 1
        if calls == 3:
            return {"observed": {"bracket": float("nan")}, "raw_extra": object()}
        return observe(path, requirements, references)

    monkeypatch.setattr(engine, "observe", malformed_last)
    metadata = execute(plan, engine)
    rows = predictions(plan)
    assert metadata["completed_cases"] == len(rows) == 3
    assert rows[-1]["outcome"] == "E"
    assert rows[-1]["app_clear"] is None
    # Standard JSON parser can read all lines; JSON NaN/Infinity are forbidden.
    for line in (plan["output"] / "predictions.jsonl").read_text().splitlines():
        json.loads(line, parse_constant=lambda value: pytest.fail(f"Nonfinite JSON constant leaked: {value}"))


def test_later_source_hash_cannot_replace_the_frozen_baseline(plan, monkeypatch):
    engine, calls = cpu_engine(monkeypatch)
    original = runner.source_hashes
    reads = 0

    def changing_hashes(*args, **kwargs):
        nonlocal reads
        reads += 1
        values = original(*args, **kwargs)
        if reads >= 2:
            values[next(iter(values))] = "0" * 64
        return values

    monkeypatch.setattr(runner, "source_hashes", changing_hashes)
    try:
        metadata = execute(plan, engine)
    except ValueError as exc:
        assert "Freeze" in str(exc) or "source" in str(exc).lower()
        assert not calls
    else:
        assert metadata["valid_frozen_run"] is False


def test_other_categories_unknown_do_not_erase_known_bracket_agreement():
    observation = {
        "observed": {"bolt": None, "nut": None, "washer": None, "bracket": 2},
        "issues": ["Other categories remain unclear"], "action": {"kind": "recapture"},
        "verification": {"passes": [{"observed": {"bracket": 2}}]},
    }
    result = runner.score_partial({"ground_truth": {"bracket": 2}}, observation, None)
    assert result["outcome"] == "C_b"
    assert result["app_clear"] is False
    assert set(result).isdisjoint({"counts_exact", "false_ready", "correct_ready", "tasks"})
    error = runner.score_partial({"ground_truth": {"bracket": 2}}, observation, "Later stage failed")
    assert error["outcome"] == "E" and error["app_clear"] is None


def test_distinct_author_counts_never_change_observer_requirements(plan, monkeypatch):
    engine, _ = cpu_engine(monkeypatch)
    observe = engine.observe
    supplied = []

    def record(path, requirements, references):
        supplied.append((dict(requirements), dict(references)))
        return observe(path, requirements, references)

    monkeypatch.setattr(engine, "observe", record)
    execute(plan, engine)
    assert [c["ground_truth"]["bracket"] for c in plan["cases"]] == [1, 2, 1]
    assert supplied == [(runner.FIXED_REQUIREMENTS, {})] * 3
    assert all(set(row["ground_truth"]) == {"bracket"} for row in predictions(plan))
