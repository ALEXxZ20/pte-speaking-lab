from contextlib import asynccontextmanager
import base64
import binascii
import hmac
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
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
    if configuration.pte_lan_mode:
        dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        if not (dist / "index.html").is_file():
            raise RuntimeError("frontend_build_required_for_lan")
        if len(configuration.pte_lan_password.get_secret_value()) < 16:
            raise RuntimeError("pte_lan_password_must_have_at_least_16_characters")

        @application.middleware("http")
        async def lan_auth(request, call_next):
            supplied = request.headers.get("Authorization", "")
            authorized = False
            if supplied.startswith("Basic "):
                try:
                    decoded = base64.b64decode(supplied[6:], validate=True).decode("utf-8")
                    username, password = decoded.split(":", 1)
                    authorized = (hmac.compare_digest(username, configuration.pte_lan_username)
                                  and hmac.compare_digest(password, configuration.pte_lan_password.get_secret_value()))
                except (ValueError, UnicodeDecodeError, binascii.Error):
                    pass
            if not authorized:
                return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="PTE Speaking Lab"'})
            return await call_next(request)

        @application.get("/{full_path:path}", include_in_schema=False)
        def frontend(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            requested = (dist / full_path).resolve()
            if requested.is_file() and requested.is_relative_to(dist.resolve()):
                return FileResponse(requested)
            return FileResponse(dist / "index.html")
    return application


app = create_app()
