"""Generation jobs and their live progress stream.

A generation is long (tens of seconds to minutes) and costs money, so the user
needs to see what is happening and be able to stop it. Each job keeps its full
event history *and* a live queue per subscriber, so a browser that connects late
or reconnects mid-run replays what it missed instead of showing a blank log.

In-memory by design: a job is meaningless after a restart because the work is
not resumable, and the artefacts it produced are already on disk.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Level(StrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    DONE = "done"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StepEvent:
    step: str
    message: str
    level: Level = Level.INFO
    asset_key: str | None = None
    at: str = field(default_factory=_now)

    def dump(self) -> dict:
        return asdict(self) | {"level": self.level.value}


@dataclass
class AssetResult:
    key: str
    label: str
    status: str                       # "ok" | "failed" | "skipped"
    path: str | None = None
    error: str | None = None
    #: Present only for scale-critical assets (§4 composite pipeline).
    scale_check: dict | None = None
    px_per_mm: float | None = None
    usd: float = 0.0

    def dump(self) -> dict:
        return asdict(self)


class Job:
    def __init__(self, product_id: str, asset_keys: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.product_id = product_id
        self.asset_keys = asset_keys
        self.status = JobStatus.QUEUED
        self.events: list[StepEvent] = []
        self.assets: dict[str, AssetResult] = {}
        self.error: str | None = None
        self.spend_inr: float = 0.0
        self.started_at = _now()
        self.finished_at: str | None = None

        self._subscribers: list[asyncio.Queue] = []
        self._cancel = asyncio.Event()

        #: Strong reference to the running task. asyncio holds only a *weak*
        #: reference to tasks, so a fire-and-forget create_task() can be garbage
        #: collected mid-run and the job would stall silently. The registry
        #: holds the job, the job holds the task.
        self.task: asyncio.Task | None = None

    # --- progress --------------------------------------------------------

    def emit(self, step: str, message: str, level: Level = Level.INFO, asset_key: str | None = None) -> StepEvent:
        event = StepEvent(step=step, message=message, level=level, asset_key=asset_key)
        self.events.append(event)
        for queue in self._subscribers:
            # Never block the pipeline on a slow or dead reader.
            queue.put_nowait(event)
        return event

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        # Replay history so a late or reconnecting client sees the whole run.
        for event in self.events:
            queue.put_nowait(event)

        if self.is_finished:
            # The sentinel was broadcast when the job ended, before this queue
            # existed. Without replaying it the stream would hang forever on a
            # job that is already over — which is exactly what a client does
            # when it reconnects to fetch the log of a completed run.
            queue.put_nowait(None)
        else:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    # --- lifecycle -------------------------------------------------------

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def is_finished(self) -> bool:
        return self.status in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled(self.id)

    def finish(self, status: JobStatus, error: str | None = None) -> None:
        self.status = status
        self.error = error
        self.finished_at = _now()
        self.emit("done", error or f"Finished: {status.value}",
                  Level.ERROR if status is JobStatus.FAILED else Level.DONE)
        for queue in self._subscribers:
            queue.put_nowait(None)  # sentinel: closes the SSE stream

    # --- serialisation ---------------------------------------------------

    def dump(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "status": self.status.value,
            "error": self.error,
            "spend_inr": round(self.spend_inr, 2),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "asset_keys": self.asset_keys,
            "assets": {k: v.dump() for k, v in self.assets.items()},
            "events": [e.dump() for e in self.events],
        }


class JobCancelled(RuntimeError):
    def __init__(self, job_id: str):
        super().__init__(f"Job {job_id} cancelled by user.")


class JobRegistry:
    """Recent jobs, newest first. Bounded so a long session cannot grow forever."""

    MAX = 50

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self, product_id: str, asset_keys: list[str]) -> Job:
        job = Job(product_id, asset_keys)
        self._jobs[job.id] = job
        if len(self._jobs) > self.MAX:
            for stale in list(self._jobs)[: len(self._jobs) - self.MAX]:
                if self._jobs[stale].status in (
                    JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED
                ):
                    del self._jobs[stale]
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def for_product(self, product_id: str) -> list[Job]:
        return [j for j in self._jobs.values() if j.product_id == product_id]

    def active_for_product(self, product_id: str) -> Job | None:
        return next(
            (j for j in self.for_product(product_id)
             if j.status in (JobStatus.QUEUED, JobStatus.RUNNING)),
            None,
        )


_registry: JobRegistry | None = None


def get_registry() -> JobRegistry:
    global _registry
    if _registry is None:
        _registry = JobRegistry()
    return _registry
