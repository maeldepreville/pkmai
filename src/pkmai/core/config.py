from dataclasses import dataclass
from pathlib import Path
import yaml


# =========================
# Config
# =========================

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass
class Config:
    vault_path: Path
    ignored_dirs: list[str]
    notes_root_dir: str

    author_mirror_dir: str
    author_mirror_prefix: str
    author_mirror_section_title: str
    author_min_chars: int
    author_max_note_chars: int
    author_model_path: Path
    author_n_ctx: int
    author_n_threads: int
    author_max_tokens: int
    author_temperature: float
    author_repeat_penalty: float
    author_overwrite_existing: bool
    author_cache_db_path: Path

    link_model_name: str
    link_similarity_threshold: float
    max_links_per_note: int
    link_min_note_chars: int
    link_section_title: str
    link_cache_db_path: Path
    link_allow_rewrite_related_section: bool
    link_insert_only_if_missing: bool


def load_config(config_path: Path = CONFIG_PATH) -> Config:
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return Config(
        vault_path=Path(raw["vault"]["path"]),
        ignored_dirs=raw["vault"]["ignored_dirs"],
        notes_root_dir=raw["vault"]["notes_root_dir"],
        author_mirror_dir=raw["author_mirror"]["output_dir"],
        author_mirror_prefix=raw["author_mirror"]["prefix"],
        author_mirror_section_title=raw["author_mirror"]["section_title"],
        author_min_chars=raw["author_mirror"]["min_chars"],
        author_max_note_chars=raw["author_mirror"]["max_note_chars"],
        author_model_path=Path(raw["author_mirror"]["model"]["path"]),
        author_n_ctx=raw["author_mirror"]["model"]["n_ctx"],
        author_n_threads=raw["author_mirror"]["model"]["n_threads"],
        author_max_tokens=raw["author_mirror"]["model"]["max_tokens"],
        author_temperature=raw["author_mirror"]["model"]["temperature"],
        author_repeat_penalty=raw["author_mirror"]["model"]["repeat_penalty"],
        author_overwrite_existing=raw["author_mirror"]["overwrite_existing"],
        author_cache_db_path=Path(raw["author_mirror"]["cache"]["db_path"]),
        link_model_name=raw["auto_links"]["embedding"]["model_name"],
        link_similarity_threshold=raw["auto_links"]["similarity_threshold"],
        max_links_per_note=raw["auto_links"]["max_links_per_note"],
        link_min_note_chars=raw["auto_links"]["min_note_chars"],
        link_section_title=raw["auto_links"]["section_title"],
        link_cache_db_path=Path(raw["auto_links"]["cache"]["db_path"]),
        link_allow_rewrite_related_section=raw["auto_links"][
            "allow_rewrite_related_section"
        ],
        link_insert_only_if_missing=raw["auto_links"]["insert_only_if_missing"],
    )
