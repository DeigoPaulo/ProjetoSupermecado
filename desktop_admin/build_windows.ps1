param([ValidatePattern('^\d+\.\d+$')][string]$PythonVersion = '3.12')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root '.build-venv'
$Python = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $Python)) { & py "-$PythonVersion" -m venv $Venv }
& $Python -m pip install -r (Join-Path $Root 'requirements.txt') pyinstaller
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name DeTecAdmin --icon (Join-Path $Root 'assets\deigo-admin-cart.ico') --distpath (Join-Path $Root 'dist') (Join-Path $Root 'app.py')
Write-Host "Executavel criado em $Root\dist\DeTecAdmin.exe"