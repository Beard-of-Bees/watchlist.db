import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database
import scheduler
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    scheduler.start_scheduler(
        username=settings.letterboxd_username,
        tmdb_api_key=settings.tmdb_api_key,
        country=settings.country,
        cron_expr=settings.refresh_schedule,
    )
    yield
    scheduler.stop_scheduler()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    films = await database.get_all_films()
    last_updated = await database.get_last_updated()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "films": films,
            "last_updated": last_updated,
            "is_refreshing": scheduler.get_refresh_state(),
        },
    )


@app.post("/refresh")
async def refresh(background_tasks: BackgroundTasks):
    if scheduler.get_refresh_state():
        return {"status": "already_running"}

    background_tasks.add_task(
        scheduler.run_refresh,
        settings.letterboxd_username,
        settings.tmdb_api_key,
        settings.country,
    )
    return {"status": "started"}
