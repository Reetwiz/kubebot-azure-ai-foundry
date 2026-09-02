$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    winget install --id Python.Python.3.12 --exact --accept-package-agreements --accept-source-agreements
}

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    winget install --id Kubernetes.kubectl --exact --accept-package-agreements --accept-source-agreements
}

python -m pip install --user pipx
python -m pipx ensurepath
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
python -m pipx install --force $ProjectRoot

Write-Host "KubeBot installed. Open a new terminal and run: kubebot"