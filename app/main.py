from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api import comments, jobs, logs, metrics, posts, scheduler, sources
from app.db.session import SessionLocal
from app.services.scheduler_service import BackgroundScheduler


background_scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    background_scheduler.start()
    try:
        yield
    finally:
        await background_scheduler.stop()


app = FastAPI(title="Reddit Crawler", version="1.0.0", lifespan=lifespan)

app.include_router(sources.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(metrics.router)
app.include_router(scheduler.router)
app.include_router(jobs.router)
app.include_router(logs.router)


@app.get("/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    finally:
        db.close()
