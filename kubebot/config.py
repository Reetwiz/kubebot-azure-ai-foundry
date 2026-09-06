"""Environment configuration and constants shared across the app."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_config_path, user_data_path
from rich.prompt import Confirm, Prompt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = user_config_path("kubebot", appauthor=False)
CONFIG_FILE = CONFIG_DIR / ".env"
RUNNING_FROM_SOURCE = (PROJECT_ROOT / "pyproject.toml").is_file()


def _dotenv_paths():
    yield CONFIG_FILE
    if RUNNING_FROM_SOURCE:
        yield Path.cwd() / ".env"
        if PROJECT_ROOT != Path.cwd():
            yield PROJECT_ROOT / ".env"


for dotenv_path in _dotenv_paths():
    load_dotenv(dotenv_path)

INSTALL_DATA_ROOT = Path(sys.prefix) / "share" / "kubebot"
DATA_ROOT = INSTALL_DATA_ROOT if (INSTALL_DATA_ROOT / "RAG_Inputdocs").exists() else PROJECT_ROOT

LLM_PROVIDER = os.getenv("KUBEBOT_LLM_PROVIDER", "").strip().lower()

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1-mini")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_FALLBACK = os.getenv("KUBEBOT_OLLAMA_FALLBACK", "true").strip().lower() in ("1", "true", "yes", "on")

# Named chat deployments KubeBot is allowed to switch between at runtime via
# '/model' (see kubebot.llm.switch_model). These must already exist in the
# Azure AI Foundry resource -- switching NEVER creates or deploys a new model,
# it only points the running app at a different existing deployment, and
# fails loudly if the requested one doesn't exist/isn't reachable.
# Format: "label1=deployment-name1,label2=deployment-name2"
_RAW_MODEL_OPTIONS = os.getenv(
    "AZURE_OPENAI_CHAT_DEPLOYMENTS",
    "mini=gpt-4.1-mini,standard=gpt-4.1",
)


def _parse_model_options(raw: str) -> dict:
    options = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        label, deployment = pair.split("=", 1)
        label = label.strip().lower()
        deployment = deployment.strip()
        if label and deployment:
            options[label] = deployment
    return options


MODEL_OPTIONS = _parse_model_options(_RAW_MODEL_OPTIONS)
# Always make sure the currently configured default deployment is reachable
# under some label, even if it wasn't listed in AZURE_OPENAI_CHAT_DEPLOYMENTS.
if AZURE_OPENAI_CHAT_DEPLOYMENT not in MODEL_OPTIONS.values():
    MODEL_OPTIONS.setdefault("current", AZURE_OPENAI_CHAT_DEPLOYMENT)

PERSIST_DIR = user_data_path("kubebot", appauthor=False) / "chroma_db" / (LLM_PROVIDER or "default")

DOC_PATHS = [
    DATA_ROOT / "RAG_Inputdocs/aks_troubleshooting.txt",
    DATA_ROOT / "RAG_Inputdocs/application_errors_guide.txt",
]

WEB_DOC_URLS = [
    "https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
    "https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/",
    "https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/",
    "https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#container-states",
    "https://kubernetes.io/docs/concepts/configuration/overview/",
    "https://kubernetes.io/docs/tasks/debug/debug-cluster/",
    "https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/troubleshoot-deployment-errors",
    "https://learn.microsoft.com/en-us/azure/aks/concepts-network",
    "https://learn.microsoft.com/en-us/azure/aks/troubleshooting",
    "https://learn.microsoft.com/en-us/azure/aks/concepts-storage",
    "https://learn.microsoft.com/en-us/azure/aks/concepts-scale",
]

# DEV/PROD verbosity flag. Set KUBEBOT_ENV=development in .env for verbose
# tool-call tracing, RAG debug prints, and full tracebacks on error. Defaults
# to production (minimal output) so a demo/prod session stays clean.
KUBEBOT_ENV = os.getenv("KUBEBOT_ENV", "production").strip().lower()
DEV_MODE = KUBEBOT_ENV in ("dev", "development")

# Cap on how many user turns we keep in context. Bounds token usage/latency/cost
# on long sessions instead of resending the entire (ever-growing) history every turn.
MAX_TURNS = 6


def configure_provider(force_prompt: bool = False):
    """Resolve the model provider, prompting only during an interactive launch."""
    global LLM_PROVIDER, PERSIST_DIR, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY

    if LLM_PROVIDER and not force_prompt:
        if LLM_PROVIDER not in ("azure", "ollama"):
            raise RuntimeError("KUBEBOT_LLM_PROVIDER must be 'azure' or 'ollama'")
        validate_provider()
        PERSIST_DIR = user_data_path("kubebot", appauthor=False) / "chroma_db" / LLM_PROVIDER
        return

    if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY and not force_prompt:
        LLM_PROVIDER = "azure"
        PERSIST_DIR = user_data_path("kubebot", appauthor=False) / "chroma_db" / LLM_PROVIDER
        return

    if not sys.stdin.isatty() and not force_prompt:
        raise RuntimeError(
            "No model provider configured. Set KUBEBOT_LLM_PROVIDER=ollama, or configure Azure OpenAI."
        )

    from kubebot.console import console

    console.print("[yellow]No Azure OpenAI credentials were found.[/yellow]")
    choice = Prompt.ask(
        "Model provider",
        choices=["ollama", "azure"],
        default="ollama",
        console=console,
    )
    if choice == "azure":
        AZURE_OPENAI_ENDPOINT = Prompt.ask("Azure OpenAI endpoint", console=console).strip()
        AZURE_OPENAI_API_KEY = Prompt.ask("Azure OpenAI API key", password=True, console=console).strip()
        LLM_PROVIDER = "azure"
        validate_provider()
        PERSIST_DIR = user_data_path("kubebot", appauthor=False) / "chroma_db" / LLM_PROVIDER
        if force_prompt or Confirm.ask("Save these settings for future launches?", default=True, console=console):
            _save_azure_settings()
        return

    LLM_PROVIDER = "ollama"
    PERSIST_DIR = user_data_path("kubebot", appauthor=False) / "chroma_db" / LLM_PROVIDER
    _save_settings(
        [
            "KUBEBOT_LLM_PROVIDER=ollama",
            f"OLLAMA_BASE_URL={OLLAMA_BASE_URL}",
            f"OLLAMA_CHAT_MODEL={OLLAMA_CHAT_MODEL}",
            f"OLLAMA_EMBEDDING_MODEL={OLLAMA_EMBEDDING_MODEL}",
        ]
    )
    console.print(f"Using local Ollama at [cyan]{OLLAMA_BASE_URL}[/cyan].")


def _save_azure_settings():
    _save_settings(
        [
            "KUBEBOT_LLM_PROVIDER=azure",
            f"AZURE_OPENAI_ENDPOINT={AZURE_OPENAI_ENDPOINT}",
            f"AZURE_OPENAI_API_KEY={AZURE_OPENAI_API_KEY}",
            f"AZURE_OPENAI_API_VERSION={AZURE_OPENAI_API_VERSION}",
            f"AZURE_OPENAI_CHAT_DEPLOYMENT={AZURE_OPENAI_CHAT_DEPLOYMENT}",
            f"AZURE_OPENAI_EMBEDDING_DEPLOYMENT={AZURE_OPENAI_EMBEDDING_DEPLOYMENT}",
        ]
    )


def _save_settings(lines):
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        CONFIG_DIR.chmod(0o700)
    temporary_file = CONFIG_FILE.with_suffix(".tmp")
    descriptor = os.open(temporary_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write("\n".join([*lines, ""]))
        stream.flush()
        os.fsync(stream.fileno())
    temporary_file.replace(CONFIG_FILE)


def validate_provider():
    if LLM_PROVIDER == "azure" and (not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY):
        raise RuntimeError("Azure requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY")


def offer_ollama_fallback(error: Exception) -> bool:
    """Offer an interactive local fallback after Azure startup fails."""
    global LLM_PROVIDER, PERSIST_DIR

    if LLM_PROVIDER != "azure" or not OLLAMA_FALLBACK or not sys.stdin.isatty():
        return False

    from kubebot.console import console

    console.print(f"[yellow]Azure OpenAI startup failed:[/yellow] {error}")
    if not Confirm.ask("Continue with local Ollama?", default=True, console=console):
        return False
    LLM_PROVIDER = "ollama"
    PERSIST_DIR = user_data_path("kubebot", appauthor=False) / "chroma_db" / LLM_PROVIDER
    return True
