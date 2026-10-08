"""Arithmetic and source-span checks, independent of model fluency or accuracy."""

import pytest

from kitguard.instructions import RevisionIntent, apply_intent

CURRENT = {"bolt": 2, "nut": 2, "washer": 2, "bracket": 1}


def intent(part="washer", part_text="washer", operation="set", quantity_text="3"):
    return RevisionIntent.model_validate(
        {
            "changes": [
                {"part": part, "part_text": part_text, "operation": operation, "quantity_text": quantity_text}
            ],
            "clarification": None,
        }
    )


def test_set_and_relative_changes_preserve_every_unmentioned_quantity():
    assert apply_intent(intent(), "Set washer to 3.", CURRENT) == {**CURRENT, "washer": 3}
    assert apply_intent(intent(operation="remove", quantity_text="one"), "Remove one washer.", CURRENT) == {
        **CURRENT,
        "washer": 1,
    }


@pytest.mark.parametrize(
    "number,instruction",
    [
        ("3", "Set washer to 4."),
        ("1", "Set washer to 12."),
        ("1", "Set washer to 1.5."),
        ("1", "Set washer to -1."),
        ("one", "Remove someone washer."),
    ],
)
def test_no_clamping_rounding_partial_numbers_or_embedded_words(number, instruction):
    with pytest.raises(ValueError):
        apply_intent(intent(quantity_text=number), instruction, CURRENT)


@pytest.mark.parametrize(
    "number,instruction",
    [
        ("4", "Set washer to 4."),
        ("-1", "Set washer to -1."),
        ("1.5", "Set washer to 1.5."),
        ("1000000", "Add 1000000 washer."),
    ],
)
def test_exact_but_invalid_quantity_is_a_business_rejection(number, instruction):
    with pytest.raises(ValueError):
        apply_intent(intent(quantity_text=number), instruction, CURRENT)


def test_known_unit_suffix_and_english_plural_are_grounded():
    assert (
        apply_intent(intent(part_text="와셔", quantity_text="3개"), "와셔를 3개로 설정해 주세요.", CURRENT)[
            "washer"
        ]
        == 3
    )
    assert (
        apply_intent(intent(quantity_text="one", operation="remove"), "Reduce washers by one.", CURRENT)[
            "washer"
        ]
        == 1
    )


def test_unknown_part_referent_and_unstated_number_do_not_become_edits():
    with pytest.raises(ValueError):
        apply_intent(
            intent(part_text="those", quantity_text="one", operation="add"), "Increase those by one.", CURRENT
        )
    with pytest.raises(ValueError):
        apply_intent(intent(quantity_text="1", operation="add"), "Add a little more washer.", CURRENT)


def test_conflicting_edits_and_zero_total_are_rejected():
    duplicate = intent()
    duplicate.changes.append(duplicate.changes[0])
    with pytest.raises(ValueError):
        apply_intent(duplicate, "Set washer to 3.", CURRENT)
    all_zero = RevisionIntent.model_validate(
        {
            "changes": [
                {"part": p, "part_text": p, "quantity_text": "0", "operation": "set"} for p in CURRENT
            ],
            "clarification": None,
        }
    )
    with pytest.raises(ValueError):
        apply_intent(all_zero, "bolt 0 nut 0 washer 0 bracket 0", CURRENT)


def test_explicit_clarification_cannot_apply_existing_changes():
    payload = intent()
    payload.clarification = "Need the exact count"
    with pytest.raises(ValueError):
        apply_intent(payload, "Set washer to 3.", CURRENT)
