"""The FastAPI application: settings, storage, API clients and background jobs created once, the REST routers under
/api, and the renderer's static files (render.css, fit.js) under /api/static."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import annotations, documents, edits, glossary, library, reading, rendering, translation
from .api.deps import Services
from .clients import make_clients
from .core.config import Settings, load_settings
from .core.jobs import JobManager
from .core.library import LibraryStore
from .core.store import DocumentStore
from .pipeline.glossary import Glossary
from .pipeline.render import STATIC

log = logging.getLogger("uvicorn.error")

ROUTERS = [documents, translation, rendering, edits, library, annotations, glossary, reading]


def create_app(settings: Settings | None = None, **client_kwargs) -> FastAPI:
    """The app for `settings` (default: the environment and .env). `client_kwargs` go to the API clients (tests pass
    an in-process `transport`)."""
    settings = settings or load_settings()
    if settings.spends_credits:
        log.warning(
            "Using real APIs (bodhan=%s, openrouter=%s): calls spend credits",
            settings.bodhan_base_url,
            settings.openrouter_base_url,
        )
    bodhan, openrouter = make_clients(settings, **client_kwargs)
    services = Services(
        settings=settings,
        store=DocumentStore(settings.data_dir / "documents"),
        library=LibraryStore(settings.data_dir / "library.json"),
        glossary=Glossary(settings.data_dir / "glossary.json"),
        jobs=JobManager(),
        bodhan=bodhan,
        openrouter=openrouter,
    )

    @asynccontextmanager
    async def lifespan(app):
        """Close the API clients when the app shuts down."""
        yield
        await bodhan.aclose()
        await openrouter.aclose()

    app = FastAPI(title="Panna", lifespan=lifespan)
    app.state.services = services
    for module in ROUTERS:
        app.include_router(module.router)
    app.mount("/api/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def revalidate_static(request, call_next):
        """Make the browser revalidate the renderer's static files, which change with the code."""
        response = await call_next(request)
        if request.url.path.startswith("/api/static/"):  # render.css / fit.js change with the renderer
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app
