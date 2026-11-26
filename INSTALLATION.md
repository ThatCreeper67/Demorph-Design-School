# Local application installation

## Requirements

- Windows 10/11 or another system that can run the standard-library Python server.
- Python 3.10 or newer.
- Ollama installed and running locally.
- The exact model tag `qwen3.5:9b-q4_K_M` already present in Ollama.
- A current browser (Edge, Chrome, Firefox, or Safari).

The local app uses Python's standard library. Pillow is used for stronger image decoding when available; a standard-library header check is used otherwise. No install command is required. The app never downloads a model.

## Check the model

```powershell
# Run from the project root
python .\local_app.py --check
```

If Ollama is not running, start it in its own terminal with `ollama serve`. If the exact model is not installed, arrange for it to be installed separately; the app will not download or replace it.

## Start

```powershell
.\start_local_app.ps1
```

The startup script performs the model check and then runs the local server in the current terminal. Open **http://127.0.0.1:8765**. Keep that terminal open. Press **Ctrl+C** there to stop the application.

To start directly:

```powershell
python .\local_app.py --host 127.0.0.1 --port 8765
```

Only loopback binding is allowed. If the port is busy, choose another local port, for example `--port 8766`, and open the matching address.

## Optional local settings

Set these in PowerShell before launch:

```powershell
$env:DEMORPH_OLLAMA_URL = 'http://127.0.0.1:11434'
$env:DEMORPH_MAX_UPLOAD_MB = '25'
$env:DEMORPH_ANALYSIS_TIMEOUT = '600'
```

The upload limit is clamped to 1–100 MB. The inference timeout is in seconds. The model tag is fixed to Qwen3.5 9B.

## Local storage

The app creates `local_app_data/uploads/`, `local_app_data/history.sqlite3`, and `local_app_data/logs/app.log`. These contain local uploads, results, and diagnostics. They are excluded from version control. Keep the folder if you want to keep local history.
