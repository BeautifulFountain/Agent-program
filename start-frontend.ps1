$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "frontend")
if (-not (Test-Path -LiteralPath ".\node_modules")) {
    throw "未安装前端依赖，请先在 frontend 目录运行：pnpm install"
}
& pnpm run dev

