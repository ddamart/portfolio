from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_db, init_db
from app.routers import assets, portfolio, prices, transactions
from app.routers import import_router
from app.routers import balance as balance_router

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(settings.database_path)
    yield
    close_db()


app = FastAPI(
    title="Portfolio Manager API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets.router)
app.include_router(transactions.router)
app.include_router(portfolio.router)
app.include_router(prices.router)
app.include_router(import_router.router)
app.include_router(balance_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
