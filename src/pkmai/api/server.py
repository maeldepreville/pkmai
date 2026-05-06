import uuid
import logging
from typing import Callable

from fastapi import FastAPI, BackgroundTasks, Path as FastApiPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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


class VaultConfig(BaseModel):
    path: str
    notes_root_dir: str
    ignored_dirs: list[str]


class EmbeddingConfig(BaseModel):
    model_name: str


class CacheConfig(BaseModel):
    db_path: str


class AutoLinksConfig(BaseModel):
    enabled: bool
    similarity_threshold: float
    max_links_per_note: int
    min_note_chars: int
    section_title: str
    allow_rewrite_related_section: bool
    insert_only_if_missing: bool
    embedding: EmbeddingConfig
    cache: CacheConfig


class ModelConfig(BaseModel):
    use_custom_path: bool
    custom_path: str
    repo_id: str
    filename: str
    n_ctx: int
    n_threads: int
    max_tokens: int
    temperature: float
    repeat_penalty: float


class AuthorMirrorConfig(BaseModel):
    enabled: bool
    output_dir: str
    prefix: str
    section_title: str
    min_chars: int
    max_note_chars: int
    overwrite_existing: bool
    model: ModelConfig
    cache: CacheConfig


# The Master Payload encompassing everything
class PluginPayload(BaseModel):
    vault: VaultConfig
    auto_links: AutoLinksConfig
    author_mirror: AuthorMirrorConfig


ACTIVE_TASKS: dict[str, str] = {}


def update_task_status(task_id: str, status: str):
    """Callback function to update the global dictionary."""
    ACTIVE_TASKS[task_id] = status


def run_tracked_task(
    task_id: str,
    task_name: str,
    func: Callable,
    override_config: dict,
) -> None:
    try:
        logging.info("Starting task %s: %s", task_id, task_name)
        update_task_status(task_id, "running")

        func(
            override_config=override_config,
            status_callback=lambda msg: update_task_status(task_id, msg),
        )

        if ACTIVE_TASKS.get(task_id) not in {"completed", "failed"}:
            update_task_status(task_id, "completed")

        logging.info("Task %s completed: %s", task_id, task_name)

    except Exception as exc:
        logging.exception("Task %s failed: %s", task_id, task_name)
        update_task_status(task_id, f"failed: {type(exc).__name__}: {exc}")


@app.get("/api/v1/tasks/{task_id}")
async def get_task_status(task_id: str = FastApiPath(...)):
    status = ACTIVE_TASKS.get(task_id, "unknown")
    return JSONResponse(content={"status": status})


@app.get("/health")
async def health_check():
    return JSONResponse(
        content={"status": "online", "message": "PKM AI Server is ready."}
    )


@app.post("/api/v1/mirror/sync")
async def sync_mirrors(payload: PluginPayload, background_tasks: BackgroundTasks):
    """Triggers the Author Mirror vault sync in the background."""
    task_id = str(uuid.uuid4())
    ACTIVE_TASKS[task_id] = "Initializing..."
    
    background_tasks.add_task(
        run_tracked_task,
        task_id=task_id,
        task_name="author_mirror",
        func=author_mirror_notes.main,
        override_config=payload.model_dump(),
    )
    
    return JSONResponse(
        content={
            "task_id": task_id,
            "status": "accepted",
            "message": "Author Mirror sync started in the background.",
        }
    )


@app.post("/api/v1/links/sync")
async def sync_links(payload: PluginPayload, background_tasks: BackgroundTasks):
    """Triggers the Auto-Links vault sync in the background."""
    task_id = str(uuid.uuid4())
    ACTIVE_TASKS[task_id] = "Initializing..."

    background_tasks.add_task(
        run_tracked_task,
        task_id=task_id,
        task_name="auto_links",
        func=auto_links.main,
        override_config=payload.model_dump(),
    )

    return JSONResponse(
        content={
            "task_id": task_id,
            "status": "accepted",
            "message": "Auto-Links sync started in the background.",
        }
    )
