param(
    [switch]$Lint,
    [switch]$Build,
    [ValidateRange(1024, 65535)]
    [int]$Port = 5173
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "frontend")
if (-not (Test-Path -LiteralPath ".\node_modules\vite\bin\vite.js")) {
    throw "未安装前端依赖，请先在 frontend 目录运行：pnpm install"
}
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$nodePath = if ($nodeCommand) { $nodeCommand.Source } else { $null }
if (-not $nodePath) {
    throw "未找到 Node.js。请安装 Node.js 20 或更高版本并重启 VS Code。"
}
if ($Lint) {
    & $nodePath ".\node_modules\eslint\bin\eslint.js" "."
} elseif ($Build) {
    & $nodePath ".\node_modules\typescript\bin\tsc" "-b"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $nodePath ".\node_modules\vite\bin\vite.js" "build"
} else {
    & $nodePath ".\node_modules\vite\bin\vite.js" --host 127.0.0.1 --port $Port --strictPort
}

