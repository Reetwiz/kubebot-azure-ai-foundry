# KubeBot

KubeBot is a read-only Kubernetes troubleshooting assistant for the terminal. It combines live cluster data, a local knowledge base, and either Azure OpenAI or Ollama.

## What it does

- Inspects pods, nodes, deployments, events, logs, and resource usage.
- Switches kubeconfig contexts and namespaces without changing the host's active context.
- Blocks mutating `kubectl` verbs and access to Kubernetes Secrets.
- Uses Azure OpenAI when configured, with an optional automatic Ollama fallback.
- Runs fully locally with Ollama and requires no API key.
- Supports Linux, macOS, and Windows with Python 3.10 or newer.

## Install

Clone the repository, then use the script for your platform.

### Linux

Download the package for your distribution from the GitHub release. The primary tested families are:

- Debian and Ubuntu (`.deb`)
- Fedora and RHEL (`.rpm`)
- Arch and Manjaro (`.pkg.tar.zst`)

```bash
# Debian or Ubuntu
sudo apt install ./kubebot_0.2.0_amd64.deb

# Fedora or RHEL
sudo dnf install ./kubebot-0.2.0-1.x86_64.rpm

# Arch or Manjaro
sudo pacman -U ./kubebot-0.2.0-1-x86_64.pkg.tar.zst
```

These packages vendor KubeBot's Python libraries and a private Python runtime under `/usr/lib/kubebot`, then expose `/usr/bin/kubebot`. Installation does not modify the system Python, run `pip`, or download Python code. The existing source installer remains available:

```bash
./scripts/install-linux.sh
```

### macOS

```bash
./scripts/install-macos.sh
```

### Windows

Run PowerShell as your normal user:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install-windows.ps1
```

The scripts install Python tooling, install `kubectl` where the distribution provides it, and then install KubeBot with `pipx`. If `kubectl` is still missing, the Linux script links to the official installation guide. To install KubeBot manually:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install .
```

Flatpak is not provided. KubeBot intentionally uses the host kubeconfig, credential helpers, and `kubectl`; Flatpak sandbox permissions would make those workflows less predictable.

## Choose a model

Run `kubebot`. On the first interactive launch, KubeBot offers two providers:

- **Ollama:** no account or API key. Install Ollama, then pull `llama3.1:8b` and `nomic-embed-text`.
- **Azure OpenAI:** enter the endpoint and API key at the masked prompts. KubeBot can save them in the operating system's user config directory. On Linux and macOS, the file is created with mode `0600`.

```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

For unattended launches, copy `.env.example` to `.env` and set `KUBEBOT_LLM_PROVIDER=azure` or `KUBEBOT_LLM_PROVIDER=ollama`. Never commit `.env`.

If Azure cannot start and `KUBEBOT_OLLAMA_FALLBACK=true`, an interactive launch offers to continue with Ollama. Azure and Ollama use separate local vector stores because their embedding dimensions may differ.

## Kubernetes access

KubeBot uses the same kubeconfig and authentication helpers as your normal Kubernetes tools.

```bash
kubectl config current-context
kubectl cluster-info
kubebot
```

Use a least-privilege, read-only Kubernetes identity. KubeBot prevents mutation through its own command interface, but your kubeconfig permissions remain authoritative.

## Commands

- `/help` shows all commands.
- `/clusters` lists kubeconfig contexts.
- `/switch` selects a context for this session.
- `/namespace` selects or clears a namespace.
- `/context` shows the current target.
- `/command get pods -A` runs an allowed read-only kubectl command.
- `/model` lists or switches configured Azure deployments.
- `/clear` clears conversation history.

## Configuration

Common settings are documented in `.env.example`. LangSmith variables are optional. Local Chroma data is stored under the platform's user data directory, not in the repository.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v
python -m kubebot
```

## Releases

Tagged releases provide source archives, Python wheels, and native Linux packages. CI installs each native package in a clean Ubuntu, Fedora, or Arch container and runs `kubebot --version`. GitHub Actions publishes the artifacts for tags matching `v*`.

GitHub Releases are currently the download source. A true APT or DNF repository additionally needs a stable HTTPS host, signed repository metadata, key rotation, and index publication; installing a downloaded `.deb` with `apt install ./file.deb` does not require that infrastructure.

See [terraform-README.md](terraform-README.md) for the optional Azure AI Foundry infrastructure example.
