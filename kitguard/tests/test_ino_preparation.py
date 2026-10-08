"""ROI engineering boundaries on invented coordinates, not visual ground truth."""

import pytest

from scripts.prepare_ino_bracket_validation import choose_view, parse_rows


def test_full_target_frame_stays_full_and_unknown_classes_not_relabelled():
    rows = parse_rows("0 .5 .5 .2 .2")
    view, error = choose_view(rows, 1000, 600)
    assert error is None and view == {"kind": "full_image", "roi": [0, 0, 1000, 600], "count": 1}


def test_foreign_object_within_padding_rejects_roi_instead_of_dropping_it():
    rows = parse_rows("0 .5 .5 .2 .2\n1 .62 .5 .04 .2")
    view, error = choose_view(rows, 1000, 600)
    assert view is None and error == "roi_touches_non0_author_bbox"


def test_two_targets_have_one_union_and_no_double_counted_sources():
    rows = parse_rows("0 .4 .5 .1 .2\n0 .6 .5 .1 .2\n2 .9 .9 .04 .04")
    view, error = choose_view(rows, 1000, 600)
    assert error is None
    assert view["count"] == 2 and view["roi"][0] < 350 and view["roi"][2] > 650


@pytest.mark.parametrize("text,reason", [
    ("0 .5 .5 .2 .2\n1 .99 .99 .2 .2", "author_bbox_outside_origin"),
    ("0 .5 .5 .02 .02", "target_bbox_too_small"),
    ("1 .5 .5 .2 .2", "no_author_class0"),
    ("\n".join(["0 .5 .5 .2 .2"] * 4), "author_class0_count_over_3"),
])
def test_fixed_exclusions_preserve_bad_source_scope(text, reason):
    assert choose_view(parse_rows(text), 1000, 600) == (None, reason)


@pytest.mark.parametrize("text", ["0 nan .5 .2 .2", "10 .5 .5 .2 .2", "0 .5 .5 -.1 .2", "0 1 2 3"])
def test_invalid_author_rows_fail_closed(text):
    with pytest.raises(ValueError):
        parse_rows(text)
