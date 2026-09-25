from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.api.health import router as health_router
from app.api.assets import router as assets_router
from app.api.comparisons import router as comparisons_router
from app.api.runs import router as runs_router
from app.config import Settings
from app.persistence.database import migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        await run_in_threadpool(migrate, configuration.database_path)
        yield

    application = FastAPI(title="PTE Speaking Lab", version="0.1.0", lifespan=lifespan)
    application.state.settings = configuration
    application.include_router(health_router)
    application.include_router(assets_router)
    application.include_router(comparisons_router)
    application.include_router(runs_router)
    return application


app = create_app()
