# PKM AI

Local, private AI orchestration for Personal Knowledge Management (PKM). 

This project bridges a local Python backend with an Obsidian frontend, allowing you to enrich your markdown vault using local Large Language Models (LLMs) and vector embeddings ; entirely offline and without subscription APIs.

## Features

- **Semantic Auto-Links:** Scans your vault, computes embeddings for each note using `sentence-transformers`, and automatically injects contextual wikilinks to conceptually similar notes.
- **Author Mirror (Thesis / Antithesis):** Uses a local LLM (via `llama.cpp`) to read a note and generate a dialectical response, proposing one real-world author who supports your idea and another who opposes it, complete with synthesized arguments.
- **Zero-Friction AI (Auto-Download):** No need to hunt for models. The backend will automatically download and cache a highly efficient, lightweight LLM (Qwen3.5-2B) from Hugging Face on its first run. Power users can easily toggle to use their own local `.gguf` files.
- **Obsidian Native Configuration:** Say goodbye to editing YAML files. The plugin features a comprehensive native settings menu inside Obsidian to control model paths, similarity thresholds, and ignored directories.
- **Live Status Polling:** Features a dynamic UI progress tracker in the Obsidian status bar so you always know what the background engine is processing.
- **Smart Caching:** Uses SQLite to cache document hashes and high-dimensional vectors, ensuring that AI models only process notes that have actually been modified.

## Architecture

```mermaid
graph LR
    A[Obsidian UI] -->|JSON Config Payload| B(FastAPI Server)
    B --> C{Task Router}
    C -->|Auto-Links| D[SentenceTransformers]
    C -->|Author Mirror| E[llama.cpp]
    D <--> F[(SQLite Cache)]
    E <--> F
    H -->|Auto-Downloads| E
    D --> G[Markdown Vault]
    E --> G
```

## Prerequisites

- **Python 3.10+** (Package management via [uv](https://github.com/astral-sh/uv) recommended)
- **Node.js & npm** (For compiling the Obsidian plugin)
- *(Optional)* A local `.gguf` LLM if you choose not to use the auto-downloaded default.

## Installation

**1. Backend (Python Server)**

Clone the repository and install the backend as an editable package using `uv`:

```bash
git clone https://github.com/maeldepreville/pkmai.git
cd pkmai
pip install uv
uv sync
```

*(Optional: For CLI usage only)* Copy the example configuration file. Note that if you use the Obsidian UI, it will automatically override this file:

```bash
cp config.example.yaml config.yaml
```

**2. Frontend (Obsidian Plugin)**

Navigate to your Obsidian vault's plugin directory and build the bridge:

```bash
cd /path/to/your/vault/.obsidian/plugins/pkmai-bridge
npm install
npm run build
```

Once built, open Obsidian > Settings > Community Plugins and enable PKM AI Bridge. You can now configure all your parameters directly from the Obsidian settings tab!

## Usage

### The API Server & Obsidian (Recommended)
To use the Obsidian UI buttons, the background server must be running:

```bash
pkmai serve
```

With the server listening on `localhost:8000`:

- Open the PKM AI settings in Obsidian to configure your paths and toggle your preferred AI model.
- Click the link or user icons in the Obsidian sidebar to trigger the respective background processes.
- Watch the bottom-right status bar for live polling updates (e.g., Downloading Model... ➔ Generating... ➔ Complete!).

### The CLI
The project includes a fully featured Typer CLI. You can run tasks manually from the terminal using your `config.yaml` file:

```bash
pkmai info          # View current system configuration
pkmai links         # Run the Auto-Links pipeline manually
pkmai mirror        # Run the Author Mirror pipeline manually
pkmai mirror -f     # Force regenerate mirrors, bypassing the cache
```

## Technical Stack

- **AI/ML:** `llama-cpp-python`, `sentence-transformers`, `huggingface_hub`, `numpy`
- **Backend:** `FastAPI`, `uvicorn`, `typer`, `pydantic`
- **Data:** Standard `sqlite3` (Vector binary serialization)
- **Frontend:** TypeScript, Obsidian API