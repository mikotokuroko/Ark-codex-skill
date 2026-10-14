$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Push-Location $repo
try {
    if (-not (Test-Path '.venv-windows/Scripts/python.exe')) {
        py -3.11 -m venv .venv-windows
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 is required.' }
    }
    & .venv-windows/Scripts/python.exe -m pip install -r requirements-windows.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & .venv-windows/Scripts/python.exe -m PyInstaller --noconfirm packaging/ArkCodexDeskpetWindows.spec
    if ($LASTEXITCODE -ne 0) { throw 'Windows build failed.' }
    Write-Host 'Built dist/Ark Codex Deskpet/Ark Codex Deskpet.exe'
} finally { Pop-Location }
