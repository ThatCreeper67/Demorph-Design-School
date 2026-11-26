# DEMORPH Design School

DEMORPH Design School is a local workspace for examining how a poster communicates through visual hierarchy, composition, contrast, and relationships between elements. It combines the DEMORPH Phase 5 analysis pipeline with a structured design curriculum and a local web interface.

Upload a design, optionally describe its purpose, and review an evidence-linked analysis: visible observations, likely reading flow, relationships between elements, evaluations, and possible refinements. The app is designed to support a designer's review; its model findings are drafts and should be checked against the image and brief.

## Requirements

- Python 3.10 or newer.
- Ollama installed and running locally.
- The exact Ollama model tag `qwen3.5:9b-q4_K_M` already installed. DEMORPH does not download or substitute a model.
- A current browser and a computer able to run local model inference.

## Start the app

Open PowerShell in this project directory and run:

```powershell
.\start_local_app.ps1
```

The startup script checks Ollama and the required model, then starts the local server. Open **http://127.0.0.1:8765** and keep the terminal open while using the app. Press **Ctrl+C** in that terminal to stop it.

To check the model connection without starting the app:

```powershell
python .\local_app.py --check
```

To start the server directly, or choose another local port:

```powershell
python .\local_app.py --host 127.0.0.1 --port 8765
```

The server only accepts loopback addresses, so it is intended for use on the same computer.

## Analyze a design

1. Drop a PNG, JPG/JPEG, or WEBP image into the upload area, or choose **browse files**.
2. Review the preview and image details. Add an optional brief to describe audience, context, or communication goals.
3. Select **Analyze design** and follow the actual processing stages shown in the app.
4. Review the observations, evidence, hierarchy, relationships, evaluations, and any recommendations.
5. Export a completed result as JSON or Markdown, or reopen it later from local history.

The current upload limit defaults to 25 MB and can be set from 1 to 100 MB. Analysis can take several minutes while Ollama runs the model. A cancellation request discards the result when the active model call returns; it does not interrupt Ollama mid-generation.

## Local data and privacy

DEMORPH runs the web interface and Ollama connection locally. Images are sent to the configured Ollama service (by default `http://127.0.0.1:11434`) for analysis; this project does not upload them to a DEMORPH cloud service.

Uploads, completed analysis history, and rotating diagnostic logs are stored in the ignored `local_app_data/` directory. Keep this folder to retain local history; deleting it removes that app data. Logs contain server diagnostics and exclude uploaded image bytes and model response bodies. The app does not modify the source design files.

## Configuration

Set optional values in PowerShell before starting the app:

```powershell
$env:DEMORPH_OLLAMA_URL = 'http://127.0.0.1:11434'
$env:DEMORPH_MAX_UPLOAD_MB = '25'
$env:DEMORPH_ANALYSIS_TIMEOUT = '600'
```

The upload setting is clamped to 1–100 MB. The inference timeout is in seconds. The required model tag is fixed by the app.

## Project guide

- [QUICKSTART.md](QUICKSTART.md) — step-by-step first analysis
- [INSTALLATION.md](INSTALLATION.md) — requirements, startup, settings, and local storage
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — common connection, upload, and inference issues
- [ARCHITECTURE.md](ARCHITECTURE.md) — app structure and analysis flow
- [curriculum/](curriculum/) — the Design School learning material used by the analysis pipeline
- [SHOWCASE_README.md](SHOWCASE_README.md) — showcase workflow and examples

The earlier command-line and Phase 5 pilot workflows remain available for development and historical evaluation. See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for a guided demonstration.

## Dataset and model status

The app uses Qwen through local Ollama inference; it does not fine-tune the model. The project has a 96-image working collection, but provenance and redistribution permission are unconfirmed for every image, so image files are excluded from public release. See [DATASET_AND_TRAINING.md](DATASET_AND_TRAINING.md) for details and the rights-clearance process.
