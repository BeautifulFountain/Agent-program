$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "frontend")
if (-not (Test-Path -LiteralPath ".\node_modules\vite\bin\vite.js")) {
    throw "未安装前端依赖，请先在 frontend 目录运行：pnpm install"
}
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$nodePath = if ($nodeCommand) { $nodeCommand.Source } else { $null }
if (-not $nodePath) {
    $codexNode = "C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1112-737-0_26.1112.737.0_x64__3k8sg7r9htsxt\dependencies\node\bin\node.exe"
    if (Test-Path -LiteralPath $codexNode) { $nodePath = $codexNode }
}
if (-not $nodePath) {
    throw "未找到 Node.js。请安装 Node.js 20 或更高版本并重启 VS Code。"
}
& $nodePath ".\node_modules\vite\bin\vite.js" --host 127.0.0.1 --port 5173

