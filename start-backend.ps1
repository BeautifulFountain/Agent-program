param(
    [switch]$Mock,
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "未找到虚拟环境，请先运行：python -m venv .venv"
}
Set-Location -LiteralPath $PSScriptRoot
if ($Mock) {
    $env:LLM_MOCK = "true"
    Write-Host "AgentFlow backend starting in Mock mode (no API balance will be used)."
}
& $pythonPath -m uvicorn backend.main:app --reload --host 127.0.0.1 --port $Port

