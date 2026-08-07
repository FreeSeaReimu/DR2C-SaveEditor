$ErrorActionPreference = "Stop"

$appDir = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$tempDir = Join-Path $appDir ".temp"
$releaseDir = Join-Path $appDir "release"
$distDir = Join-Path $tempDir "dist"
$workDir = Join-Path $tempDir "build"
$specDir = Join-Path $tempDir "spec"
$dataPath = Join-Path $appDir "data"
$resourcePath = Join-Path $appDir "resource"
$venvDir = Join-Path $tempDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $tempDir, $releaseDir, $distDir, $workDir, $specDir | Out-Null
if (-not (Test-Path -LiteralPath $venvPython)) {
  python -m venv $venvDir
}
& $venvPython -m pip install --disable-pip-version-check --quiet -r (Join-Path $appDir "requirements.txt") pyinstaller==6.8.0

# app.py 优先使用 vendor 中随源码保存的依赖，构建环境无需依赖全局 Python。
$env:PYTHONPATH = Join-Path $appDir "vendor"
$env:PYTHONNOUSERSITE = "1"

& $venvPython -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "DR2C-SaveEditor-1.0.2" `
  --distpath $distDir `
  --workpath $workDir `
  --specpath $specDir `
  --paths (Join-Path $appDir "vendor") `
  --add-data "$dataPath;data" `
  --add-data "$resourcePath;resource" `
  (Join-Path $appDir "app.py")

$built = Join-Path $distDir "DR2C-SaveEditor-1.0.2.exe"
if (-not (Test-Path -LiteralPath $built)) {
  throw "PyInstaller output was not found: $built"
}

$target = Join-Path $releaseDir "DR2C-SaveEditor-1.0.2.exe"
Copy-Item -LiteralPath $built -Destination $target -Force
Write-Output "Release built: $target"
