$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

python .\local_app.py --check
if ($LASTEXITCODE -ne 0) {
    throw 'Ollama or the required Qwen3.5 9B model is unavailable. See TROUBLESHOOTING.md.'
}

python .\local_app.py --host 127.0.0.1 --port 8765
