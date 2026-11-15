$ErrorActionPreference = "Stop"
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "未找到虚拟环境，请先运行：python -m venv .venv"
}
Set-Location -LiteralPath $PSScriptRoot
& $pythonPath -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

