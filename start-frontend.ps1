$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "frontend")
if (-not (Test-Path -LiteralPath ".\node_modules\vite\bin\vite.js")) {
    throw "未安装前端依赖，请先在 frontend 目录运行：pnpm install"
}
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCommand) {
    throw "未找到 Node.js，请先安装 Node.js 20 或更高版本并重启 VS Code。"
}
& $nodeCommand.Source ".\node_modules\vite\bin\vite.js" --host 127.0.0.1 --port 5173

