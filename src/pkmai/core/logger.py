import logging
from datetime import datetime
from pathlib import Path


# =========================
# Logging
# =========================

def setup_logging(log_dir: Path = Path("logs"), prefix: str = "pkmai") -> None:
    """
    Sets up the logging configuration.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f"{prefix}_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True, 
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    
    logging.info(f"Logging initialized. Writing to {log_file.name}")