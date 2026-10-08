"""Local runtime admission and data-directory ownership, independent of vision policy."""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

from .store import StateError


class DataDirectoryLease:
    """An OS-released exclusive lease, acquired before abandoned-job recovery."""

    def __init__(self, directory: Path):
        self.path = Path(directory) / ".kitguard-instance.lock"
        self.file = None

    def acquire(self):
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if not handle.read(1):
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError(
                "이 데이터 폴더는 다른 KitGuard 인스턴스가 사용 중입니다 / "
                "此数据目录已由另一个 KitGuard 实例使用，请使用已打开的工作台"
            ) from exc
        self.file = handle
        return self

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None


class InferenceGate:
    """One admitted call, including a timed-out call whose CPU/GPU thread still runs.

    There is no application inference queue. HTTP timeout or cancellation stops
    waiting but cannot pretend to stop synchronous model execution. The worker
    owns its slot until it actually returns, then a fresh request may retry.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._active = None
        self._closing = False
        self._on_idle = None

    def open(self):
        with self._lock:
            if self._active is not None:
                raise RuntimeError("Previous inference is still running")
            self._closing = False

    def reserve(self):
        with self._lock:
            if self._closing or self._active is not None:
                raise StateError(
                    "모델이 아직 처리 중입니다. 완료 후 다시 시도하세요 / "
                    "模型仍在处理上一项任务，请待其结束后重试",
                    503,
                )
            slot = _InferenceSlot(self)
            self._active = slot
            return slot

    def status(self):
        with self._lock:
            return {
                "busy": self._active is not None,
                "request_waiting": bool(self._active and self._active.request_waiting),
                "queue_capacity": 0,
            }

    def close_when_idle(self, callback):
        with self._lock:
            self._closing = True
            if self._active is not None:
                self._on_idle = callback
                return
        callback()

    def _release(self, slot):
        with self._lock:
            if self._active is not slot:
                return
            self._active = None
            callback, self._on_idle = self._on_idle, None
        if callback is not None:
            callback()


class _InferenceSlot:
    def __init__(self, gate):
        self.gate = gate
        self.started = False
        self.request_waiting = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        if not self.started:
            self.gate._release(self)

    def _invoke(self, function, args):
        try:
            return function(*args)
        finally:
            self.gate._release(self)

    @staticmethod
    def _consume_late_exception(future):
        if not future.cancelled():
            future.exception()

    async def run(self, function, *args, timeout):
        if self.started:
            raise RuntimeError("An inference reservation can only run once")
        self.started = True
        try:
            future = asyncio.get_running_loop().run_in_executor(None, self._invoke, function, args)
        except BaseException:
            self.gate._release(self)
            raise
        future.add_done_callback(self._consume_late_exception)
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        finally:
            self.request_waiting = False
