# MoneyPlant QA check — runs every test the user can execute in one command.
# PowerShell script; counterpart for bash is scripts/qa_check.sh.

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Write-Host "== MoneyPlant QA check ==" -ForegroundColor Cyan
Write-Host "Repo root: $root"

# --- Backend ------------------------------------------------------------
Push-Location (Join-Path $root "backend")
try {
    Write-Host "`n=== Backend: install ===" -ForegroundColor Cyan
    if (-not (Test-Path ".venv")) {
        python -m venv .venv
    }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Host
    & .\.venv\Scripts\python.exe -m pip install -e ".[dev]" | Out-Host

    Write-Host "`n=== Backend: migrate ===" -ForegroundColor Cyan
    & .\.venv\Scripts\alembic.exe upgrade head | Out-Host

    Write-Host "`n=== Backend: pytest ===" -ForegroundColor Cyan
    & .\.venv\Scripts\pytest.exe -v | Out-Host
} finally {
    Pop-Location
}

# --- Frontend -----------------------------------------------------------
Push-Location (Join-Path $root "apps/web")
try {
    Write-Host "`n=== Frontend: install ===" -ForegroundColor Cyan
    npm install | Out-Host

    Write-Host "`n=== Frontend: typecheck ===" -ForegroundColor Cyan
    npm run typecheck | Out-Host

    Write-Host "`n=== Frontend: lint ===" -ForegroundColor Cyan
    npm run lint | Out-Host

    Write-Host "`n=== Frontend: vitest ===" -ForegroundColor Cyan
    npm test | Out-Host

    Write-Host "`n=== Frontend: playwright ===" -ForegroundColor Cyan
    $playwrightInstalled = (& npx playwright --version) 2>$null
    if (-not $playwrightInstalled) {
        Write-Host "Installing Playwright browsers (one-time)..." -ForegroundColor Yellow
        npx playwright install --with-deps chromium | Out-Host
    }
    npm run test:e2e | Out-Host
} finally {
    Pop-Location
}

Write-Host "`n=== QA check complete ===" -ForegroundColor Green
