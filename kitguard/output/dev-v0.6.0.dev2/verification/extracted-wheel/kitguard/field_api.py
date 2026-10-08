"""Strict HTTP inputs and local exports for the fixed-state validation recorder."""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from starlette.background import BackgroundTask

from .field_archive import build_study_archive
from .field_study import render_report


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Counts(Input):
    bolt: StrictInt = Field(ge=0, le=100)
    nut: StrictInt = Field(ge=0, le=100)
    washer: StrictInt = Field(ge=0, le=100)
    bracket: StrictInt = Field(ge=0, le=100)


class NewStudy(Input):
    title: str = Field(min_length=1, max_length=100)
    source_kind: Literal["self_reported_physical", "public_replay", "engineering_fixture"]
    planned_cases: StrictInt = Field(ge=1, le=48)
    participant_code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    note: str = Field(default="", max_length=500)


def explicit_true(value):
    if value is not True:
        raise ValueError("명시적 확인이 필요합니다 / 需要明确确认")
    return value


class Confirm(Input):
    confirmed: Literal[True]
    _strict = field_validator("confirmed", mode="before")(explicit_true)


class NewCase(Input):
    label: str = Field(min_length=1, max_length=80)
    order_id: str = Field(min_length=1, max_length=80)
    expected_revision: StrictInt = Field(ge=1)
    photo_id: str = Field(min_length=1, max_length=80)
    truth: Counts
    truth_repeat: Counts
    confirmed_independent: Literal[True]
    source_note: str = Field(min_length=1, max_length=500)
    _strict = field_validator("confirmed_independent", mode="before")(explicit_true)

    @model_validator(mode="after")
    def same_truth(self):
        if self.truth != self.truth_repeat:
            raise ValueError("두 입력 수량이 다릅니다 / 两次真值输入不一致，请重新独立计数")
        return self


class Start(Input):
    method: Literal["manual", "kitguard"]


class Finish(Input):
    outcome: Literal["completed", "failed", "abandoned"]
    manual_counts: Counts | None = None
    check_id: str | None = Field(default=None, min_length=1, max_length=80)
    note: str = Field(default="", max_length=1000)


def study_router(studies):
    router = APIRouter(prefix="/api/studies")

    @router.get("")
    async def list_studies():
        return {"studies": studies.list()}

    @router.post("", status_code=201)
    async def create(body: NewStudy):
        return {"study": studies.create(body.model_dump())}

    @router.get("/{study_id}")
    async def get(study_id: str):
        return {"study": studies.get(study_id)}

    @router.post("/{study_id}/cases", status_code=201)
    async def register(study_id: str, body: NewCase):
        return {"study": studies.add_case(study_id, body.model_dump())}

    @router.post("/{study_id}/freeze")
    async def freeze(study_id: str, body: Confirm):
        return {"study": studies.freeze(study_id)}

    @router.post("/{study_id}/cases/{case_id}/start")
    async def start(study_id: str, case_id: str, body: Start):
        return studies.start(study_id, case_id, body.method)

    @router.post("/{study_id}/trials/{trial_id}/finish")
    async def finish(study_id: str, trial_id: str, body: Finish):
        return {"study": studies.finish(study_id, trial_id, body.model_dump())}

    @router.post("/{study_id}/close")
    async def close(study_id: str, body: Confirm):
        return {"study": studies.close(study_id)}

    @router.get("/{study_id}/export")
    async def export(study_id: str):
        payload = studies.export(study_id)
        return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="kitguard-{payload["study"]["id"]}.json"'})

    @router.get("/{study_id}/report.html")
    async def report(study_id: str):
        payload = studies.export(study_id)
        return HTMLResponse(render_report(payload), headers={
            "Content-Disposition": f'attachment; filename="kitguard-{payload["study"]["id"]}-report.html"',
        })

    @router.get("/{study_id}/evidence.zip")
    async def evidence(study_id: str):
        path = await asyncio.to_thread(build_study_archive, studies, study_id)
        return FileResponse(path, media_type="application/zip", filename=f"kitguard-{study_id}-study.zip",
                            background=BackgroundTask(path.unlink, missing_ok=True))

    return router
