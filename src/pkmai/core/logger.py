import logging
from datetime import datetime
from pathlib import Path


# =========================
# Logging
# =========================


def cleanup_old_logs(log_dir: Path, pattern: str, keep: int = 20) -> None:
    """
    Keeps only the newest `keep` log files matching `pattern`.
    """
    if keep <= 0:
        return

    if not log_dir.exists():
        return

    logs = sorted(
        log_dir.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for old_log in logs[keep:]:
        try:
            old_log.unlink()
        except OSError:
            pass


def setup_logging(
    log_dir: Path = Path("logs"),
    prefix: str = "pkmai",
    keep_last: int = 20,
) -> Path:
    """
    Sets up file + stream logging for one task run.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{prefix}_{timestamp}.log"

    cleanup_old_logs(log_dir, f"{prefix}_*.log", keep=keep_last - 1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    logging.info("Logging initialized. Writing to %s", log_file.name)
    logging.info("Log retention active. Keeping last %d %s logs.", keep_last, prefix)

    return log_file
