import logging
from pathlib import Path
from huggingface_hub import hf_hub_download


def get_or_download_model(repo_id: str, filename: str) -> Path:
    """
    Checks if a model exists locally. If not, downloads it from Hugging Face.
    """
    models_dir = Path.cwd() / "model"
    models_dir.mkdir(exist_ok=True)

    logging.info("Resolving model: %s/%s", repo_id, filename)

    try:
        model_path = hf_hub_download(
            repo_id=repo_id, filename=filename, local_dir=str(models_dir)
        )
        return Path(model_path)
    except Exception as e:
        raise RuntimeError(
            f"Failed to download or locate model {filename} from {repo_id}: {e}"
        )
