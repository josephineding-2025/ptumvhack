param(
    [string]$VenvDir = ".venv"
)

$ErrorActionPreference = "Stop"

Write-Host "Creating virtual environment in $VenvDir ..."
python -m venv $VenvDir

Write-Host "Activating virtual environment ..."
$activateScript = Join-Path $VenvDir "Scripts\\Activate.ps1"
. $activateScript

Write-Host "Upgrading pip ..."
python -m pip install --upgrade pip

Write-Host "Installing dependencies from requirements.txt ..."
pip install -r requirements.txt

Write-Host "Setup complete."
