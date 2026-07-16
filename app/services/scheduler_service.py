import asyncio
import contextlib
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import PipelineJob
from app.db.session import SessionLocal
from app.services.metric_service import update_due_metrics
from app.services.source_service import due_sources, scrape_source


logger = logging.getLogger("reddit_api.scheduler")


@dataclass
class RunDueResult:
    source_jobs: list[PipelineJob]
    metric_jobs: list[PipelineJob]


def run_due(db: Session) -> RunDueResult:
    source_jobs: list[PipelineJob] = []
    sources = due_sources(db)
    logger.info("Scheduler bat dau scrape bai moi | sources_due=%s", len(sources))
    for source in sources:
        try:
            job = scrape_source(db, source, job_type="scrape_new_posts")
            source_jobs.append(job)
            db.commit()
        except Exception as exc:
            logger.exception(
                "Scheduler scrape source that bai | source=%s id=%s error=%s",
                source.identifier,
                source.id,
                exc,
            )
            db.commit()
            continue
    metric_jobs = update_due_metrics(db)
    db.commit()
    logger.info(
        "Scheduler hoan tat chu ky | sources_processed=%s metrics_jobs=%s",
        len(source_jobs),
        len(metric_jobs),
    )
    return RunDueResult(source_jobs=source_jobs, metric_jobs=metric_jobs)


class BackgroundScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if not self.settings.scheduler_enabled or self._task is not None:
            if not self.settings.scheduler_enabled:
                logger.info("Scheduler dang tat | scheduler_enabled=false")
            return
        logger.info("Scheduler bat dau | poll_seconds=%s", self.settings.scheduler_poll_seconds)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("Scheduler da dung")

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
        except Exception:
            logger.exception("Scheduler chu ky that bai")
        finally:
            db.close()
