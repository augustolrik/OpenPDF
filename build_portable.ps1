$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python generate_icon.py
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name PDFeditEasy `
    --icon PDFeditEasy.ico `
    --collect-all pymupdf `
    --exclude-module pandas `
    app.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

$tesseractCandidates = @(
    "$env:LOCALAPPDATA\Programs\Tesseract-OCR",
    "C:\Program Files\Tesseract-OCR",
    "C:\Program Files (x86)\Tesseract-OCR"
)
$tesseractSource = $tesseractCandidates |
    Where-Object { Test-Path "$_\tesseract.exe" } |
    Select-Object -First 1

if (-not $tesseractSource) {
    throw "Tesseract OCR was not found."
}

$portable = Join-Path $PSScriptRoot "dist\PDFeditEasy"
$ocrTarget = Join-Path $portable "tesseract"
$tessdataTarget = Join-Path $ocrTarget "tessdata"
New-Item -ItemType Directory -Force -Path $tessdataTarget | Out-Null
Copy-Item "$tesseractSource\tesseract.exe" $ocrTarget -Force
Get-ChildItem $tesseractSource -Filter *.dll -File |
    Copy-Item -Destination $ocrTarget -Force
Copy-Item `
    "$tesseractSource\tessdata\dan.traineddata", `
    "$tesseractSource\tessdata\eng.traineddata", `
    "$tesseractSource\tessdata\osd.traineddata" `
    -Destination $tessdataTarget `
    -Force
Copy-Item "$tesseractSource\doc\LICENSE" "$ocrTarget\LICENSE-Tesseract.txt" -Force
Copy-Item "$PSScriptRoot\PORTABLE_README.txt" "$portable\README.txt" -Force

$zip = Join-Path $PSScriptRoot "dist\PDFeditEasy_Portable.zip"
Compress-Archive -Path $portable -DestinationPath $zip -CompressionLevel Optimal -Force

Write-Host ""
Write-Host "Portable folder: $portable"
Write-Host "Portable ZIP:    $zip"
