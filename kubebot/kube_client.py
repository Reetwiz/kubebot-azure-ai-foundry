"""Kubernetes client/session state: current cluster context, current
namespace pin, and a cache of API clients per kube context.

Switching only affects which context KubeBot's own API calls use; it never
rewrites the user's shared kubeconfig file, so it can't affect other
terminals/kubectl sessions.
"""

from kubernetes import client, config

# Session-scoped active cluster override. None => use kubeconfig's current-context.
CURRENT_CONTEXT = None

# Session-scoped default namespace pin, set via '/namespace'. None means tools
# that support cluster-wide queries default to ALL namespaces instead of
# silently assuming the literal Kubernetes namespace named "default".
CURRENT_NAMESPACE = None

# Cache of API clients per kube context. Every tool used to call
# config.load_kube_config() + client.XApi() on every single invocation, which
# re-parses the kubeconfig file and re-runs the (potentially slow, e.g.
# kubelogin/Azure exec plugin) auth setup on EVERY tool call, even repeated
# calls to the same cluster within one turn or session. Loading once per
# context and reusing the client cuts that overhead dramatically.
_client_cache: dict = {}


def resolve_context_name():
    """Return the display name of the cluster context KubeBot is currently targeting."""
    if CURRENT_CONTEXT:
        return CURRENT_CONTEXT
    try:
        _, active_context = config.list_kube_config_contexts()
        return active_context['name'] if active_context else "Unknown"
    except Exception:
        return "Unknown"


def get_clients(context_name=None):
    """Return cached {core_v1, apps_v1, custom} API clients for a kube context,
    loading kubeconfig only the first time a given context is used."""
    key = context_name or "__default__"
    if key not in _client_cache:
        config.load_kube_config(context=context_name)
        _client_cache[key] = {
            "core_v1": client.CoreV1Api(),
            "apps_v1": client.AppsV1Api(),
            "custom": client.CustomObjectsApi(),
        }
    return _client_cache[key]


def cache_clients(context_name, core_v1, apps_v1, custom):
    """Populate the client cache directly (used after switch_cluster's own
    verification call, so that verified client isn't discarded/re-created)."""
    _client_cache[context_name] = {"core_v1": core_v1, "apps_v1": apps_v1, "custom": custom}


def effective_namespace(namespace: str) -> str:
    """Resolve the namespace a tool call should target: an explicit namespace
    argument always wins; otherwise fall back to the session-pinned namespace
    (see '/namespace'), or "" (= all namespaces) if nothing is pinned. This is
    what stops the literal "default" namespace from being silently assumed
    when the user actually means "every namespace"."""
    if namespace:
        return namespace
    return CURRENT_NAMESPACE or ""


def find_pod_namespace(v1, pod_name: str):
    """Search ALL namespaces for an exact pod name match.

    Returns the namespace string if exactly one match is found, a list of
    namespace names if multiple pods share that name, or None if not found
    anywhere in the cluster.
    """
    matches = [
        p.metadata.namespace
        for p in v1.list_pod_for_all_namespaces(watch=False).items
        if p.metadata.name == pod_name
    ]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return matches


def list_context_names():
    """Return all context names found in the local kubeconfig."""
    contexts, _ = config.list_kube_config_contexts()
    return [c['name'] for c in (contexts or [])]


def set_current_context(context_name):
    global CURRENT_CONTEXT
    CURRENT_CONTEXT = context_name


def set_current_namespace(namespace):
    global CURRENT_NAMESPACE
    CURRENT_NAMESPACE = namespace
