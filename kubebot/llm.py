"""Chat and embedding model setup for Azure OpenAI or local Ollama."""

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from kubebot import config
from kubebot.console import console

_embeddings = None
_chat_model = None
_current_deployment = config.AZURE_OPENAI_CHAT_DEPLOYMENT


def _build_azure_chat_model(deployment: str) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
        api_key=config.AZURE_OPENAI_API_KEY,
        api_version=config.AZURE_OPENAI_API_VERSION,
        azure_deployment=deployment,
        temperature=0,
        max_tokens=4096,
    )


def init():
    """Initialize the default chat + embeddings models. Raises on failure."""
    global _chat_model, _embeddings
    try:
        if config.LLM_PROVIDER == "ollama":
            _chat_model = ChatOllama(
                base_url=config.OLLAMA_BASE_URL,
                model=config.OLLAMA_CHAT_MODEL,
                temperature=0,
            )
            _embeddings = OllamaEmbeddings(
                base_url=config.OLLAMA_BASE_URL,
                model=config.OLLAMA_EMBEDDING_MODEL,
            )
        else:
            _chat_model = _build_azure_chat_model(_current_deployment)
            _embeddings = AzureOpenAIEmbeddings(
                azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
                api_key=config.AZURE_OPENAI_API_KEY,
                api_version=config.AZURE_OPENAI_API_VERSION,
                azure_deployment=config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            )
        _chat_model.invoke([HumanMessage(content="Reply with OK.")])
        _embeddings.embed_query("health check")
    except Exception as e:
        _chat_model = None
        _embeddings = None
        raise
    console.print(f"[green]SUCCESS:[/green] {provider_name()} initialized successfully")


def get_chat_model():
    if _chat_model is None:
        init()
    return _chat_model


def get_embeddings():
    if _embeddings is None:
        init()
    return _embeddings


def current_deployment_name() -> str:
    if config.LLM_PROVIDER == "ollama":
        return config.OLLAMA_CHAT_MODEL
    return _current_deployment


def provider_name() -> str:
    return "Ollama" if config.LLM_PROVIDER == "ollama" else "Azure OpenAI"


def available_models() -> dict:
    """Label -> deployment name mapping of models KubeBot can switch to."""
    if config.LLM_PROVIDER == "ollama":
        return {"local": config.OLLAMA_CHAT_MODEL}
    return dict(config.MODEL_OPTIONS)


def switch_model(name_or_deployment: str) -> str:
    """Switch the active chat deployment to an already-existing Azure OpenAI
    deployment, identified either by its configured label (e.g. 'mini',
    'standard') or by its raw deployment name.

    Verifies the deployment is real and reachable with a minimal, cheap test
    call BEFORE committing to it. Raises ValueError if the deployment doesn't
    exist or the call fails for any reason -- the previously active model
    keeps being used in that case.

    Returns the resolved deployment name on success.
    """
    global _current_deployment, _chat_model

    if config.LLM_PROVIDER != "azure":
        raise ValueError("Runtime model switching is only available with Azure OpenAI")

    options = config.MODEL_OPTIONS
    target = options.get(name_or_deployment.strip().lower(), name_or_deployment.strip())

    candidate = _build_azure_chat_model(target)
    try:
        candidate.invoke([HumanMessage(content="ping")])
    except Exception as e:
        raise ValueError(f"Deployment '{target}' not found or unreachable: {e}") from e

    _current_deployment = target
    _chat_model = candidate
    return target
