"""Ground quantity edits in verbatim instruction spans, then calculate in code."""

import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PART_ALIASES = {
    "bolt": {"bolt", "bolts", "screw", "screws", "볼트", "나사", "螺栓", "螺丝", "螺钉"},
    "nut": {"nut", "nuts", "너트", "螺母"},
    "washer": {"washer", "washers", "와셔", "垫圈", "垫片"},
    "bracket": {"bracket", "brackets", "브래킷", "角码", "角架"},
}
ALL_ALIASES = {"all", "each", "all four", "모두", "전부", "각각", "四类", "全部", "所有", "各类"}
NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "영": 0,
    "공": 0,
    "한": 1,
    "하나": 1,
    "두": 2,
    "둘": 2,
    "세": 3,
    "셋": 3,
    "네": 4,
    "넷": 4,
    "다섯": 5,
    "여섯": 6,
    "일": 1,
    "이": 2,
    "삼": 3,
    "사": 4,
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}
CLARIFY = "부품 종류와 정확한 정수 수량을 명시해 주세요 / 请明确零件类别及精确整数数量"


class QuantityEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    part: Literal["bolt", "nut", "washer", "bracket"]
    part_text: Annotated[str, Field(min_length=1, max_length=30)]
    operation: Literal["set", "add", "remove"]
    quantity_text: Annotated[str, Field(min_length=1, max_length=30)]


class RevisionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    changes: Annotated[list[QuantityEdit], Field(max_length=8)]
    clarification: Annotated[str, Field(min_length=1, max_length=400)] | None


def _normalized(text):
    return unicodedata.normalize("NFKC", text).replace("−", "-").casefold().strip()


def _is_span(span, instruction, *, allow_plural=False):
    if not span or span not in instruction:
        return False
    # Avoid interpreting 'one' inside 'someone', or the 1 inside 12 / 1.5.
    if re.fullmatch(r"[a-z]+(?: [a-z]+)*", span):
        return bool(
            re.search(
                r"(?<![a-z])" + re.escape(span) + (r"s?" if allow_plural else "") + r"(?![a-z])", instruction
            )
        )
    if re.fullmatch(r"[+-]?\d+", span):
        return bool(re.search(r"(?<![\d.\-+负])" + re.escape(span) + r"(?!\d|\.\d)", instruction))
    return True


def apply_intent(intent, instruction, current):
    """Never clamp, infer an omitted quantity, or silently alter an unmentioned part."""
    if intent.clarification is not None or not intent.changes:
        raise ValueError(intent.clarification or CLARIFY)
    normalized = _normalized(instruction)
    result, seen = dict(current), set()
    for change in intent.changes:
        if change.part in seen:
            raise ValueError(
                "한 부품에 상충하거나 중복된 변경이 있습니다 / 同一类别有重复或冲突指令，请分开确认"
            )
        seen.add(change.part)
        part_text, number_text = _normalized(change.part_text), _normalized(change.quantity_text)
        if part_text not in PART_ALIASES[change.part] | ALL_ALIASES or not _is_span(
            part_text, normalized, allow_plural=True
        ):
            raise ValueError(CLARIFY)
        if not _is_span(number_text, normalized):
            raise ValueError(CLARIFY)
        number_text = re.sub(r"\s*(?:개|个|件)$", "", number_text).strip()
        if number_text in NUMBER_WORDS:
            quantity = NUMBER_WORDS[number_text]
        elif re.fullmatch(r"[+-]?\d{1,9}", number_text):
            quantity = int(number_text)
        else:
            raise ValueError("정확한 정수 수량만 지원합니다 / 仅支持明确的整数数量")
        if quantity < 0:
            raise ValueError("음수 수량은 사용할 수 없습니다 / 不支持负数量")
        result[change.part] = (
            quantity
            if change.operation == "set"
            else current[change.part] + quantity
            if change.operation == "add"
            else current[change.part] - quantity
        )
    if (
        any(type(value) is not int or not 0 <= value <= 3 for value in result.values())
        or not 1 <= sum(result.values()) <= 12
    ):
        raise ValueError(
            "종류별 0~3개, 총 1~12개만 지원합니다. 수량을 자동으로 줄이지 않습니다 / 每类0–3件，总计1–12件，不会自动截断数量"
        )
    return result
