"""User-declared photo documents: local bytes, no provenance authentication."""

import hashlib
import json
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .schemas import Requirements


def is_digital_only(order):
    # Presence also fails closed on malformed persisted document metadata.
    return bool(order.get("demo_source")) or "document_source" in order


def digital_source(order):
    return order.get("document_source") if "document_source" in order else order.get("demo_source")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


class DocumentStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_note: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2048)
    license_note: str | None = Field(default=None, max_length=500)

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value):
        if not value:
            return None
        try:
            parsed = urlsplit(value)
            valid = (parsed.scheme in {"https", "http"} and bool(parsed.hostname)
                     and parsed.username is None and parsed.password is None
                     and not any(ord(c) < 33 or ord(c) == 127 for c in value)
                     and "\\" not in value)
            _port = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid HTTP(S) source declaration URL") from exc
        if not valid:
            raise ValueError("Only HTTP(S) source declarations without credentials are accepted")
        return value


class NewPhotoDocument(DocumentStatement):
    title: str = Field(min_length=1, max_length=100)
    requirements: Requirements
    confirmed_digital_only: Literal[True]

    @field_validator("confirmed_digital_only", mode="before")
    @classmethod
    def explicit_digital(cls, value):
        if value is not True:
            raise ValueError("Please explicitly confirm digital-only review")
        return value


class DocumentSource(DocumentStatement):
    schema_version: StrictInt = Field(ge=1, le=1)
    kind: Literal["user_declared_photo"]
    verification: Literal["user_declared_unverified"]
    physical_completion_allowed: Literal[False]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    storage_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_root_photo_id: str = Field(min_length=1, max_length=80)
    declared_at: str = Field(min_length=1, max_length=80)
    statement_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("physical_completion_allowed", mode="before")
    @classmethod
    def forbid_physical(cls, value):
        if value is not False:
            raise ValueError("Photo documents are strictly digital-only")
        return value


def bind_source(statement, photo, stamp):
    statement = DocumentStatement.model_validate(statement).model_dump()
    source = {**statement, "schema_version": 1, "kind": "user_declared_photo",
              "verification": "user_declared_unverified", "physical_completion_allowed": False,
              "source_sha256": photo["source_sha256"], "storage_sha256": photo["sha256"],
              "original_root_photo_id": photo["id"], "declared_at": stamp,
              "statement_sha256": digest(statement)}
    return {**source, "binding_sha256": digest(source)}


def verify_document_source(order, root):
    from .store import StateError

    try:
        original = order["document_source"]
        source = DocumentSource.model_validate(original).model_dump()
        statement = {key: source[key] for key in DocumentStatement.model_fields}
        initial = next(p for p in order["photos"] if p["id"] == source["original_root_photo_id"])
        valid = (not order.get("demo_source") and source == original
                 and source["statement_sha256"] == digest(statement)
                 and source["binding_sha256"] == digest({k: v for k, v in source.items() if k != "binding_sha256"})
                 and initial.get("kind") == "root_photo"
                 and initial.get("document_source") == source and root.get("document_source") == source
                 and initial.get("source_sha256") == root.get("source_sha256") == source["source_sha256"]
                 and initial.get("sha256") == root.get("sha256") == source["storage_sha256"])
    except (ValueError, TypeError, KeyError, StopIteration):
        valid = False
    if not valid:
        raise StateError("자료 출처 선언·원본 연결이 바뀌었습니다 / 资料来源声明或根图绑定已改变")
    return source
