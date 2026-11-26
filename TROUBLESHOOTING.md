# Troubleshooting the local app

## The browser says it cannot connect

Check that the startup terminal still shows the local address. The app is bound to loopback at `http://127.0.0.1:8765`. If that port is occupied, run `python .\local_app.py --port 8766` and open `http://127.0.0.1:8766`.

## Ollama is unavailable

Start Ollama in its own terminal (`ollama serve`) and run:

```powershell
python .\local_app.py --check
ollama list
```

The exact tag `qwen3.5:9b-q4_K_M` must be present. The app does not auto-download or substitute models.

## The image is rejected

Use PNG, JPG/JPEG, or WEBP. The client checks file size and preview decoding; the server also checks the actual image signature, decodes it when Pillow is available, and limits very large dimensions. A renamed, corrupt, empty, or oversized file is rejected before analysis. The original image is not resized.

## Analysis is slow or times out

Local inference may take several minutes depending on the computer and image. Keep the app and Ollama running. The server uses `DEMORPH_ANALYSIS_TIMEOUT` (default 600 seconds). Increase it for a slower local system if needed. A timeout is recorded as a failed analysis, never as a completed result.

## Result says it could not be validated

An empty, malformed, truncated, or cross-reference-invalid Qwen response is not shown as successful. Retry once. If it repeats, check `local_app_data/logs/app.log` and the local Ollama service.

## A cancellation takes time

Ollama generation is not interrupted mid-call. Cancel marks the job and discards its result once that call returns. The UI explains this wait and does not report a cancelled job as complete.

## History or exports are missing

Completed analyses and their original uploads are stored in `local_app_data/`. Do not remove that folder if you want to preserve history. JSON and Markdown exports are available from each completed result.

## Logs

The rotating local log is `local_app_data/logs/app.log`. It records server diagnostics, not uploaded image bytes or model response bodies. Error details are kept out of the browser UI.
