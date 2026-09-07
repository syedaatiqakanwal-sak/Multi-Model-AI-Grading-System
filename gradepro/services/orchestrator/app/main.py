from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from app.config import settings
from api.routes.jobs import router as jobs_router
from api.routes.settings import router as settings_router
from api.routes.models import router as models_router
from api.routes.rubrics import router as rubrics_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="GradePro Orchestrator",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach routes
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(models_router, prefix="/api/v1")
app.include_router(rubrics_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "orchestrator"}


Instrumentator().instrument(app).expose(app)
