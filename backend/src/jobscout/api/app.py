"""FastAPI application factory.

A factory (``create_app()``) rather than a module-level ``app = ...``:
construction order stays explicit (settings -> provider -> routers),
and tests can build isolated apps with injected settings/providers.
The module-level ``app`` at the bottom exists only as the uvicorn
target (``uvicorn jobscout.api.app:app``).

FastAPI over Flask/Django (PLAN.md "Backend API framework"): async
end-to-end matches the async SQLAlchemy stack, pydantic request/
response validation matches the codebase's typing discipline, and the
auto-generated OpenAPI docs at /docs are the demo surface for free.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jobscout.api.routes import applications, copilot, jobs, profiles
from jobscout.config import Settings, get_settings
from jobscout.llm import LLMProvider, llm_from_settings
from jobscout.matching.embeddings import EmbeddingProvider, provider_from_settings


def create_app(
    settings: Settings | None = None,
    provider: EmbeddingProvider | None = None,
    llm: LLMProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Job Scout API",
        description="Ranked job matches with visible reasoning.",
        version="0.1.0",
    )
    app.state.embedding_provider = provider or provider_from_settings(settings)
    app.state.llm = llm if llm is not None else llm_from_settings(settings)

    # The Next.js dev server is a different origin (localhost:3000 vs
    # 8000), so the browser needs CORS consent. Wide-open methods but a
    # pinned origin list: this API is personal, not public.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs.router)
    app.include_router(profiles.router)
    app.include_router(applications.router)
    app.include_router(copilot.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
