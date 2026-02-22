# NAVO RADIO — запуск Icecast с конфигом проекта
$IcecastDir = "C:\Program Files\Icecast"
$ConfigPath = Join-Path $PSScriptRoot "..\config\icecast.xml"

if (-not (Test-Path "$IcecastDir\bin\icecast.exe")) {
    Write-Host "Icecast not found at $IcecastDir" -ForegroundColor Red
    Write-Host "Install from https://icecast.org/download/"
    exit 1
}

Write-Host "Starting Icecast (port 8001, mount /live)..." -ForegroundColor Green
Write-Host "Stream URL: http://localhost:8001/live"
Push-Location $IcecastDir
& "$IcecastDir\bin\icecast.exe" -c $ConfigPath
Pop-Location
