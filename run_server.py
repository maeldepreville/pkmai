import multiprocessing
import os

# Must be set before torch / transformers / sentence_transformers are imported.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import uvicorn
from pkmai.api.server import app


if __name__ == "__main__":
    multiprocessing.freeze_support()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )