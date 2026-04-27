from fastapi import FastAPI, BackgroundTasks  # BackgroundTasks to avoid freezing the UI
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
    path: str
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


@app.get("/health")
async def health_check():
    return JSONResponse(
        content={"status": "online", "message": "PKM AI Server is ready."}
    )


@app.post("/api/v1/mirror/sync")
async def sync_mirrors(payload: PluginPayload, background_tasks: BackgroundTasks):
    """Triggers the Author Mirror vault sync in the background."""
    background_tasks.add_task(author_mirror_notes.main, override_config=payload.model_dump())
    return JSONResponse(
        content={
            "status": "accepted",
            "message": "Author Mirror sync started in the background.",
        }
    )


@app.post("/api/v1/links/sync")
async def sync_links(payload: PluginPayload, background_tasks: BackgroundTasks):
    """Triggers the Auto-Links vault sync in the background."""
    background_tasks.add_task(auto_links.main, override_config=payload.model_dump())
    return JSONResponse(
        content={
            "status": "accepted",
            "message": "Auto-Links sync started in the background.",
        }
    )
