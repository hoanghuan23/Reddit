import asyncio
import contextlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import PipelineJob
from app.db.session import SessionLocal
from app.services.metric_service import update_due_metrics
from app.services.source_service import due_sources, scrape_source


@dataclass
class RunDueResult:
    source_jobs: list[PipelineJob]
    metric_job: PipelineJob | None


def run_due(db: Session) -> RunDueResult:
    source_jobs: list[PipelineJob] = []
    for source in due_sources(db):
        try:
            job = scrape_source(db, source)
            source_jobs.append(job)
            db.commit()
        except Exception:
            db.commit()
            continue
    metric_job = update_due_metrics(db)
    db.commit()
    return RunDueResult(source_jobs=source_jobs, metric_job=metric_job)


class BackgroundScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if not self.settings.scheduler_enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            await asyncio.to_thread(self._run_once)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.settings.scheduler_poll_seconds)
            except asyncio.TimeoutError:
                pass

    def _run_once(self) -> None:
        db = SessionLocal()
        try:
            run_due(db)
        finally:
            db.close()
