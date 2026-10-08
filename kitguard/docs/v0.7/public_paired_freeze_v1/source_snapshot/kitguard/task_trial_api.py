"""Strict local API for the separate full-task trial recorder."""
import json
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Header, Request
from fastapi.responses import Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from .store import StateError


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def strict_true(value):
    if value is not True:
        raise ValueError("需要本人明确勾选 / 직접 확인이 필요합니다")
    return value


Code = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")]


class Counts(Input):
    bolt: StrictInt = Field(ge=0, le=100)
    nut: StrictInt = Field(ge=0, le=100)
    washer: StrictInt = Field(ge=0, le=100)
    bracket: StrictInt = Field(ge=0, le=100)


class Confirm(Input):
    confirmed: Literal[True]
    _true = field_validator("confirmed", mode="before")(strict_true)


class Create(Input):
    title: str = Field(min_length=1, max_length=100)
    source_kind: Literal["self_reported_physical", "engineering_fixture"] = "self_reported_physical"
    scale: Literal["pilot9", "study27"]
    participant_codes: list[Code] = Field(min_length=3, max_length=3)
    host_code: Code
    source_declaration: str = Field(min_length=1, max_length=1000)
    capture_session: str = Field(min_length=1, max_length=100)
    consent_confirmed: StrictBool
    real_source_confirmed: StrictBool

    @model_validator(mode="after")
    def declared_source(self):
        if self.source_kind == "self_reported_physical" and not (self.real_source_confirmed and self.consent_confirmed):
            raise ValueError("实物批次需要实物与自愿同意声明 / 실물·동의 선언이 필요합니다")
        if self.source_kind == "engineering_fixture" and (self.real_source_confirmed or self.consent_confirmed):
            raise ValueError("工程fixture不得声明真实实物或真人同意 / fixture는 실물·사람 동의를 선언하지 않습니다")
        return self


class DoubleCount(Input):
    counts: Counts
    counts_repeat: Counts
    independent_confirmed: Literal[True]
    note: str = Field(default="", max_length=1000)
    _true = field_validator("independent_confirmed", mode="before")(strict_true)

    @model_validator(mode="after")
    def matching(self):
        if self.counts != self.counts_repeat:
            raise ValueError("两次实物计数不一致 / 두 실물 계수가 다릅니다")
        return self


class Start(Input):
    consent_confirmed: Literal[True]
    fresh_setup_confirmed: Literal[True]
    _true = field_validator("consent_confirmed", "fresh_setup_confirmed", mode="before")(strict_true)


class Observe(Input):
    counts: Counts


class Action(Input):
    kind: Literal["captured_photo", "uploaded_photo", "moved_parts", "added_removed_parts", "requested_help", "other"]
    note: str = Field(min_length=1, max_length=1000)


class Submit(Input):
    outcome: Literal["completed", "failed", "abandoned"]
    takeover: StrictBool
    note: str = Field(default="", max_length=1000)


class Review(DoubleCount):
    reviewer_code: Code
    unchanged_since_submission_confirmed: Literal[True]
    _unchanged = field_validator("unchanged_since_submission_confirmed", mode="before")(strict_true)


class DownloadForm(Input):
    token: str = Field(min_length=16, max_length=200)


class AccessDownloadForm(DownloadForm):
    participant_tokens: str = Field(min_length=2, max_length=2000)


def attachment(payload, filename):
    """A native browser attachment, generated in memory and never cached."""
    return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store", "Pragma": "no-cache",
                             "X-Content-Type-Options": "nosniff"})


async def download_form(request, model):
    # Default validation responses can echo the entire body when a form field
    # is missing. Never reflect download credentials into an error page.
    form = await request.form()
    if any(len(form.getlist(key)) != 1 for key in form):
        raise StateError("下载表单字段重复 / 다운로드 양식 필드 중복", 422)
    try:
        return model.model_validate(dict(form))
    except ValidationError:
        raise StateError("下载表单无效 / 다운로드 양식 오류", 422) from None


def task_trial_router(trials):
    router = APIRouter(prefix="/api/task-trials")
    Token = Annotated[str, Header(alias="X-Trial-Token", min_length=16, max_length=200)]

    @router.post("", status_code=201)
    async def create(body: Create):
        return trials.create(body.model_dump())

    @router.get("/{batch_id}")
    async def get(batch_id: str, token: Token):
        return {"batch": trials.get(batch_id, token)}

    @router.post("/{batch_id}/freeze")
    async def freeze(batch_id: str, body: Confirm, token: Token):
        return {"batch": trials.freeze(batch_id, token)}

    @router.post("/{batch_id}/tasks/{task_id}/setup")
    async def setup(batch_id: str, task_id: str, body: DoubleCount, token: Token):
        return {"batch": trials.setup(batch_id, task_id, token, body.model_dump())}

    @router.post("/{batch_id}/tasks/{task_id}/start")
    async def start(batch_id: str, task_id: str, body: Start, token: Token):
        return {"batch": trials.start(batch_id, task_id, token, body.model_dump())}

    @router.post("/{batch_id}/tasks/{task_id}/observe")
    async def observe(batch_id: str, task_id: str, body: Observe, token: Token):
        return {"batch": trials.observe(batch_id, task_id, token, body.model_dump())}

    @router.post("/{batch_id}/tasks/{task_id}/reveal-change")
    async def reveal_change(batch_id: str, task_id: str, body: Confirm, token: Token):
        return {"batch": trials.reveal_change(batch_id, task_id, token)}

    @router.post("/{batch_id}/tasks/{task_id}/actions")
    async def action(batch_id: str, task_id: str, body: Action, token: Token):
        return {"batch": trials.log_action(batch_id, task_id, token, body.model_dump())}

    @router.post("/{batch_id}/tasks/{task_id}/submit")
    async def submit(batch_id: str, task_id: str, body: Submit, token: Token):
        return {"batch": trials.submit(batch_id, task_id, token, body.model_dump())}

    @router.post("/{batch_id}/tasks/{task_id}/review-start")
    async def review_start(batch_id: str, task_id: str, body: Confirm, token: Token):
        return {"batch": trials.begin_review(batch_id, task_id, token)}

    @router.post("/{batch_id}/tasks/{task_id}/review")
    async def review(batch_id: str, task_id: str, body: Review, token: Token):
        return {"batch": trials.review(batch_id, task_id, token, body.model_dump())}

    @router.post("/{batch_id}/close")
    async def close(batch_id: str, body: Confirm, token: Token):
        return {"batch": trials.close(batch_id, token)}

    @router.get("/{batch_id}/export")
    async def export(batch_id: str, token: Token):
        payload = trials.export(batch_id, token)
        return attachment(payload, f"kitguard-{batch_id}-full-task.json")

    @router.post("/{batch_id}/export-download")
    async def export_download(batch_id: str, request: Request):
        # Native form POST keeps credentials out of the download URL and retains
        # the original user click, including in browsers that block blob saves.
        body = await download_form(request, DownloadForm)
        return attachment(trials.export(batch_id, body.token), f"kitguard-{batch_id}-full-task.json")

    @router.post("/{batch_id}/access-download")
    async def access_download(batch_id: str, request: Request):
        # The server stores hashes only. The host must already possess every
        # participant token; this endpoint cannot recover or reissue a lost key.
        body = await download_form(request, AccessDownloadForm)
        with trials.store.connect() as db:
            batch = trials._get(db, batch_id)
        trials.host(batch, body.token)
        try:
            tokens = json.loads(body.participant_tokens)
        except (ValueError, TypeError):
            raise StateError("入口数据格式不正确 / 접근 데이터 형식 오류", 422) from None
        if not isinstance(tokens, dict) or set(tokens) != set(batch["participant_codes"]):
            raise StateError("须提供本批次全部参与者入口 / 이 배치의 모든 참여자 토큰이 필요합니다", 422)
        for participant, value in tokens.items():
            if not isinstance(value, str) or not 16 <= len(value) <= 200:
                raise StateError("参与者入口格式不正确 / 참여자 토큰 형식 오류", 422)
            if trials.role(batch, value) != participant:
                raise StateError("参与者入口与代号不匹配 / 참여자 토큰과 코드 불일치", 403)
        base = str(request.base_url).rstrip("/") + "/static/trials.html#"
        link = lambda value: base + urlencode({"batch": batch_id, "token": value})
        return attachment({"host": link(body.token), "participants": {p: link(t) for p, t in tokens.items()}},
                          f"{batch_id}-PRIVATE-access.json")

    return router
