from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.product_routes import router as product_router
from .api.job_routes import router as job_router
from .api.weekly_routes import router as weekly_router
from .api.analyst_report_routes import router as analyst_report_router
from .api.preliminary_report_routes import router as preliminary_report_router
from .api.single_stat_routes import router as single_stat_router
from .api.tiers_routes import router as tiers_router
from .api.weekly_learning_library_routes import router as weekly_learning_library_router
from .api.routes import router
from .db import initialize_database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="football_26 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(product_router)
app.include_router(job_router)
app.include_router(weekly_router)
app.include_router(analyst_report_router)
app.include_router(preliminary_report_router)
app.include_router(single_stat_router)
app.include_router(tiers_router)
app.include_router(weekly_learning_library_router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": "football_26",
        "status": "ok",
        "ui": "Run the Vite development server from ui/ or serve ui/dist in production.",
    }
