<#
.SYNOPSIS
    Aurati Studio — one-command setup + launch (Windows 10/11).

.DESCRIPTION
    Creates the Python 3.12 venv, installs backend + frontend dependencies on
    first run, then starts the FastAPI backend and the Vite dev server together.
    Re-running is cheap: dependency installs are skipped unless -Setup is passed
    or requirements.txt / package.json changed.

.EXAMPLE
    .\run.ps1
    .\run.ps1 -Setup          # force a clean dependency reinstall
    .\run.ps1 -DryRun         # launch with IMAGE_PROVIDER=dryrun (zero API spend)
    .\run.ps1 -BackendOnly    # API only, no frontend
#>
[CmdletBinding()]
param(
    [switch]$Setup,
    [switch]$DryRun,
    [switch]$BackendOnly
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Venv = Join-Path $Root 'venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
$StampDir = Join-Path $Root '.stamps'

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Write-Ok($msg)   { Write-Host "  + $msg" -ForegroundColor Green }

# --- 1. locate Python 3.12 --------------------------------------------------
# mediapipe and onnxruntime publish no wheels for 3.13/3.14, so the venv is
# pinned to 3.12 regardless of what `python` resolves to on PATH.
function Resolve-Python312 {
    $viaLauncher = (& { py -3.12 -c "import sys; print(sys.executable)" } 2>$null)
    if ($LASTEXITCODE -eq 0 -and $viaLauncher) { return $viaLauncher.Trim() }

    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python312\python.exe"
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

# --- 2. venv ----------------------------------------------------------------
if ($Setup -and (Test-Path $Venv)) {
    Write-Step 'Removing existing venv (-Setup)'
    Remove-Item -Recurse -Force $Venv
}

if (-not (Test-Path $VenvPy)) {
    $py312 = Resolve-Python312
    if (-not $py312) {
        Write-Host ''
        Write-Host 'Python 3.12 was not found.' -ForegroundColor Red
        Write-Host 'Aurati Studio needs 3.12 — MediaPipe (landmark detection) and'
        Write-Host 'onnxruntime (background removal) ship no wheels for 3.13 or 3.14.'
        Write-Host ''
        Write-Host 'Install it with:' -ForegroundColor Yellow
        Write-Host '    winget install --id Python.Python.3.12 --exact --scope user'
        Write-Host ''
        Write-Host 'It installs side-by-side; your existing Python stays the default.'
        exit 1
    }
    Write-Step "Creating venv from $py312"
    & $py312 -m venv $Venv
    Write-Ok 'venv created'
}

# --- 3. backend deps --------------------------------------------------------
New-Item -ItemType Directory -Force $StampDir | Out-Null
$reqPath = Join-Path $Root 'backend\requirements.txt'
$reqHash = (Get-FileHash $reqPath -Algorithm SHA256).Hash
$reqStamp = Join-Path $StampDir 'requirements.sha256'

if ($Setup -or -not (Test-Path $reqStamp) -or (Get-Content $reqStamp -Raw).Trim() -ne $reqHash) {
    Write-Step 'Installing backend dependencies (first run downloads ~700 MB of ML wheels)'
    & $VenvPy -m pip install --upgrade pip --quiet
    & $VenvPy -m pip install -r $reqPath
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency install failed.' }
    Set-Content -Path $reqStamp -Value $reqHash -Encoding utf8
    Write-Ok 'backend dependencies ready'
} else {
    Write-Ok 'backend dependencies up to date'
}

# --- 4. frontend deps -------------------------------------------------------
$FrontDir = Join-Path $Root 'frontend'
if (-not $BackendOnly) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw 'Node.js not found on PATH. Install Node 20+ from https://nodejs.org, or use -BackendOnly.'
    }
    if ($Setup -or -not (Test-Path (Join-Path $FrontDir 'node_modules'))) {
        Write-Step 'Installing frontend dependencies'
        Push-Location $FrontDir
        try {
            npm install
            if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
        } finally { Pop-Location }
        Write-Ok 'frontend dependencies ready'
    } else {
        Write-Ok 'frontend dependencies up to date'
    }
}

# --- 5. .env ----------------------------------------------------------------
$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root '.env.example') $envFile
    Write-Warn 'Created .env from .env.example — add your GOOGLE_API_KEY before generating.'
}
if ($DryRun) {
    $env:IMAGE_PROVIDER = 'dryrun'
    Write-Warn 'Dry-run mode: placeholder images, zero API spend.'
}

# --- 6. launch --------------------------------------------------------------
$backendPort = 8000
$frontendPort = 5173
foreach ($line in (Get-Content $envFile -ErrorAction SilentlyContinue)) {
    if ($line -match '^\s*BACKEND_PORT\s*=\s*(\d+)')  { $backendPort  = [int]$Matches[1] }
    if ($line -match '^\s*FRONTEND_PORT\s*=\s*(\d+)') { $frontendPort = [int]$Matches[1] }
}

Write-Step "Starting backend on http://127.0.0.1:$backendPort"
$backendArgs = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$backendPort", '--reload')
$backend = Start-Process -FilePath $VenvPy -ArgumentList $backendArgs `
    -WorkingDirectory (Join-Path $Root 'backend') -PassThru -NoNewWindow

try {
    if ($BackendOnly) {
        Write-Ok "API docs: http://127.0.0.1:$backendPort/docs"
        Write-Host 'Press Ctrl+C to stop.'
        Wait-Process -Id $backend.Id
    } else {
        Write-Step "Starting frontend on http://localhost:$frontendPort"
        Push-Location $FrontDir
        try {
            npm run dev -- --port $frontendPort
        } finally { Pop-Location }
    }
} finally {
    if ($backend -and -not $backend.HasExited) {
        Write-Step 'Stopping backend'
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
