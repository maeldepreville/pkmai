from fastapi import FastAPI, BackgroundTasks  # BackgroundTasks to avoid freezing the UI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pkmai.tasks import author_mirror_notes
from pkmai.tasks import auto_links

app = FastAPI(
    title="PKM AI Server",
    description="Local API for Personal Knowledge Management AI tools.",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return JSONResponse(
        content={"status": "online", "message": "PKM AI Server is ready."}
    )


@app.post("/api/v1/mirror/sync")
async def sync_mirrors(background_tasks: BackgroundTasks):
    """Triggers the Author Mirror vault sync in the background."""
    background_tasks.add_task(author_mirror_notes.main)
    return JSONResponse(
        content={
            "status": "accepted",
            "message": "Author Mirror sync started in the background.",
        }
    )


@app.post("/api/v1/links/sync")
async def sync_links(background_tasks: BackgroundTasks):
    """Triggers the Auto-Links vault sync in the background."""
    background_tasks.add_task(auto_links.main)
    return JSONResponse(
        content={
            "status": "accepted",
            "message": "Auto-Links sync started in the background.",
        }
    )
