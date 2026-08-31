param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $projectRoot "web"

if (-not $PythonPath) {
    $projectDrive = Split-Path -Qualifier $projectRoot
    $candidatePythonPaths = @(
        @(
            $(if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX "python.exe" }),
            "$projectDrive\Anaconda\anaconda\envs\rag_chroma\python.exe",
            "$env:USERPROFILE\anaconda3\envs\rag_chroma\python.exe"
        ) | Where-Object { $_ -and (Test-Path $_) }
    )

    if ($candidatePythonPaths.Count -gt 0) {
        $PythonPath = $candidatePythonPaths[0]
    }
    else {
        $PythonPath = (Get-Command python -ErrorAction Stop).Source
    }
}

if (-not (Test-Path $PythonPath)) {
    throw "未找到 Python 解释器：$PythonPath"
}

$pnpmPath = (Get-Command pnpm -ErrorAction SilentlyContinue).Source
if (-not $pnpmPath) {
    throw "未找到 pnpm，请先安装 Node.js 和 pnpm，并确认 pnpm 已加入 PATH。"
}

if (-not $env:APP_JWT_SECRET) {
    $randomBytes = New-Object byte[] 48
    $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $randomGenerator.GetBytes($randomBytes)
    $randomGenerator.Dispose()
    $env:APP_JWT_SECRET = [Convert]::ToBase64String($randomBytes)
}

if (-not $env:APP_CORS_ORIGINS) {
    $env:APP_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
}

$backendCommand = "& '$PythonPath' -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000"
$frontendCommand = "& '$pnpmPath' dev --host 127.0.0.1"

Start-Process powershell.exe `
    -WorkingDirectory $projectRoot `
    -ArgumentList "-NoExit", "-Command", $backendCommand

Start-Process powershell.exe `
    -WorkingDirectory $webRoot `
    -ArgumentList "-NoExit", "-Command", $frontendCommand

Write-Host "CleanPilot AI 正在启动：" -ForegroundColor Green
Write-Host "后端：http://127.0.0.1:8000"
Write-Host "前端：http://127.0.0.1:5173"
Write-Host "请保留新打开的两个终端窗口。"

Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:5173"
