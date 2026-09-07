$ErrorActionPreference = "Stop"
$Repository = if ($env:KUBEBOT_GITHUB_REPOSITORY) { $env:KUBEBOT_GITHUB_REPOSITORY } else { "Reetwiz/kubebot-azure-ai-foundry" }

if ($env:KUBEBOT_SKIP_SYSTEM_PACKAGES -ne "1") {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        winget install --id Python.Python.3.12 --exact --accept-package-agreements --accept-source-agreements
    }

    if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
        winget install --id Kubernetes.kubectl --exact --accept-package-agreements --accept-source-agreements
    }
}

python -m pip install --user pipx
python -m pipx ensurepath

if ($env:KUBEBOT_INSTALL_SOURCE) {
    $InstallSource = $env:KUBEBOT_INSTALL_SOURCE
} else {
    $Release = Invoke-RestMethod "https://api.github.com/repos/$Repository/releases/latest"
    $Wheel = $Release.assets | Where-Object { $_.name -like "*-py3-none-any.whl" } | Select-Object -First 1
    if (-not $Wheel) {
        throw "The latest release has no Python wheel."
    }
    $InstallSource = $Wheel.browser_download_url
}

python -m pipx install --force $InstallSource

Write-Host "KubeBot installed. Open a new terminal and run: kubebot"