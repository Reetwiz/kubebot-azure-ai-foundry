"""LangChain @tool-decorated functions the agent can call: cluster health,
pods, logs, metrics, namespaces, nodes, deployments, events, and AI log
analysis. All Kubernetes access goes through kubebot.kube_client so context/
namespace switching and client caching stay consistent everywhere.
"""

from kubernetes import client, config
from langchain.tools import tool
from langchain_core.messages import HumanMessage

from kubebot import kube_client, llm
from kubebot.rag import consult_knowledge_base  # noqa: F401 (re-exported into `tools`)


@tool
def check_cluster_health():
    """
    Use this tool when the user asks about:
    - Cluster status or health
    - Pod issues or failures
    - Current cluster state
    - What's wrong with the cluster
    """
    try:
        v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]

        cluster_name = kube_client.resolve_context_name()

        pods = v1.list_pod_for_all_namespaces(watch=False)
        unhealthy = []

        for pod in pods.items:
            restarts = sum(
                cs.restart_count for cs in (pod.status.container_statuses or [])
            )

            phase = pod.status.phase
            is_unhealthy = (
                phase not in ["Running", "Succeeded"] or
                restarts > 5
            )

            if is_unhealthy:
                container_info = []
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        if cs.state.waiting:
                            container_info.append(
                                f"Waiting: {cs.state.waiting.reason}"
                            )
                        elif cs.state.terminated:
                            container_info.append(
                                f"Terminated: {cs.state.terminated.reason}"
                            )

                status_detail = ", ".join(container_info) if container_info else phase

                unhealthy.append(
                    f"• Namespace: {pod.metadata.namespace} | "
                    f"Pod: {pod.metadata.name} | "
                    f"Status: {status_detail} | "
                    f"Restarts: {restarts}"
                )

        if not unhealthy:
            return f"Cluster Health: Good\nCluster: {cluster_name}\nAll pods are Running/Succeeded with acceptable restart counts."

        result = f"WARNING: Cluster: {cluster_name}\n\nUnhealthy Pods Detected:\n"
        result += "\n".join(unhealthy[:15])

        if len(unhealthy) > 15:
            result += f"\n\n... and {len(unhealthy) - 15} more pods with issues."

        return result

    except config.ConfigException as e:
        return (
            "ERROR: Could not load kubeconfig. "
            "Please ensure kubectl is configured and you have access to a cluster.\n"
            f"Details: {str(e)}"
        )
    except Exception as e:
        return f"ERROR: Error connecting to cluster: {str(e)}"


@tool
def get_pod_logs(pod_name: str, namespace: str = "", previous: bool = False):
    """
    Retrieves logs from a specific pod in the cluster.

    Args:
        pod_name: Name of the pod to get logs from
        namespace: Kubernetes namespace the pod lives in. Leave empty ("") to
            auto-detect it by searching ALL namespaces for this exact pod name --
            do NOT default to the "default" namespace unless the user explicitly
            says "default namespace".
        previous: If True, get logs from previous container instance (useful for CrashLoopBackOff)

    Use this tool when the user asks to:
    - See logs for a specific pod
    - Debug a crashing pod
    - Check what's happening in a container
    """
    try:
        v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]
        ns = kube_client.effective_namespace(namespace)

        if not ns:
            found = kube_client.find_pod_namespace(v1, pod_name)
            if found is None:
                return f"ERROR: Pod '{pod_name}' not found in any namespace."
            if isinstance(found, list):
                return (f"ERROR: Multiple pods named '{pod_name}' exist in namespaces: "
                         f"{', '.join(found)}. Specify which namespace to use.")
            ns = found

        log = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=ns,
            previous=previous,
            tail_lines=50  # Limit to last 50 lines
        )

        return f"Logs for pod '{pod_name}' in namespace '{ns}':\n\n{log}"

    except client.exceptions.ApiException as e:
        if e.status == 404:
            # Explicit namespace was given but wrong -- try to auto-locate the pod elsewhere.
            fallback = kube_client.find_pod_namespace(v1, pod_name)
            if isinstance(fallback, str) and fallback != ns:
                return (f"ERROR: Pod '{pod_name}' not found in namespace '{ns}'. "
                         f"Did you mean namespace '{fallback}'? Re-run with that namespace.")
            return f"ERROR: Pod '{pod_name}' not found in namespace '{ns}'"
        else:
            return f"ERROR: Error retrieving logs: {e.reason}"
    except Exception as e:
        return f"ERROR: {str(e)}"


@tool
def find_pods_by_keyword(keyword: str):
    """
    Searches for pods across ALL namespaces that contain a specific keyword.

    Use this when the user mentions a service name (e.g., "billing", "sftp", "auth")
    but doesn't provide the exact pod ID.

    Args:
        keyword: The string to search for in pod names (e.g., "billing")
    """
    try:
        v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]

        pods = v1.list_pod_for_all_namespaces(watch=False)
        matches = []

        for pod in pods.items:
            if keyword.lower() in pod.metadata.name.lower():
                status = pod.status.phase
                restarts = sum(cs.restart_count for cs in (pod.status.container_statuses or []))
                matches.append(
                    f"• Namespace: {pod.metadata.namespace} | "
                    f"Name: {pod.metadata.name} | "
                    f"Status: {status} | "
                    f"Restarts: {restarts}"
                )

        if not matches:
            return f"No pods found matching keyword '{keyword}'."

        result = f"**Found {len(matches)} pods matching '{keyword}':**\n"
        result += "\n".join(matches[:20])  # Limit to 20 to avoid overwhelming the context
        return result

    except Exception as e:
        return f"ERROR: Error searching pods: {str(e)}"


@tool
def list_all_pods(namespace: str = "", status_filter: str = ""):
    """
    Lists REAL pods currently in the cluster (ground truth, never guessed/remembered).

    - If `namespace` is empty (default), returns a per-namespace pod COUNT summary
      plus the cluster-wide total across ALL namespaces (or just the session-pinned
      namespace, see '/namespace', if one is set). This stays fast and small even
      on clusters with hundreds of pods.
    - If `namespace` is given, returns the full list of pod names, status, and
      restart counts for that one namespace.
    - `status_filter` (optional) restricts results to a specific phase, e.g.
      "Running", "Pending", "Failed", "Succeeded".

    Use this tool whenever the user asks to list/see/show all pods or asks how many
    pods exist, in one namespace or the whole cluster. Do not fabricate pod names
    from memory of earlier answers -- always call this tool for current, real data.
    Never assume the literal "default" namespace for a cluster-wide request; pass
    namespace="" for that.

    Args:
        namespace: restrict to a single namespace (default: "" = all namespaces, summary mode)
        status_filter: restrict to a specific pod phase (default: "" = no filter)
    """
    try:
        v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]
        ns = kube_client.effective_namespace(namespace)

        if ns:
            pods = v1.list_namespaced_pod(namespace=ns).items
        else:
            pods = v1.list_pod_for_all_namespaces(watch=False).items

        if status_filter:
            pods = [p for p in pods if p.status.phase == status_filter]

        if not ns:
            counts = {}
            for p in pods:
                counts[p.metadata.namespace] = counts.get(p.metadata.namespace, 0) + 1
            lines = [f"**Total pods: {len(pods)}**\n"]
            for pod_ns, count in sorted(counts.items()):
                lines.append(f"- {pod_ns}: {count} pod(s)")
            lines.append("\n(Call this tool again with a `namespace` argument to see the full pod list for one namespace.)")
            return "\n".join(lines)

        lines = [f"**Pods in '{ns}'** ({len(pods)} total):\n"]
        for p in pods:
            restarts = sum(cs.restart_count for cs in (p.status.container_statuses or []))
            lines.append(f"- {p.metadata.name} | Status: {p.status.phase} | Restarts: {restarts}")
        return "\n".join(lines)

    except Exception as e:
        return f"ERROR: Error listing pods: {str(e)}"


@tool
def check_resource_usage(namespace: str = ""):
    """
    Checks the CPU and Memory usage of pods.

    Use this when the user asks about performance, 'heavy' pods, or memory usage.
    Note: Requires Kubernetes Metrics Server to be installed.

    Args:
        namespace: restrict to a single namespace. Leave empty ("") to check
            usage across ALL namespaces -- do not assume "default" for a
            cluster-wide request.
    """
    try:
        custom_api = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["custom"]
        ns = kube_client.effective_namespace(namespace)

        try:
            if ns:
                metrics = custom_api.list_namespaced_custom_object(
                    group="metrics.k8s.io", version="v1beta1",
                    namespace=ns, plural="pods"
                )
            else:
                metrics = custom_api.list_cluster_custom_object(
                    group="metrics.k8s.io", version="v1beta1", plural="pods"
                )
        except client.exceptions.ApiException as e:
            if e.status == 404:
                return "ERROR: Metrics Server not detected. Unable to fetch CPU/Memory stats."
            raise e

        usage_data = []
        for item in metrics['items']:
            pod_name = item['metadata']['name']
            pod_namespace = item['metadata']['namespace']
            cpu_usage = 0
            mem_usage = 0

            for container in item['containers']:
                # CPU is in nanocores (n), Memory in Kibibytes (Ki)
                c_cpu = container['usage']['cpu']
                c_mem = container['usage']['memory']

                # Convert CPU to millicores (m)
                if c_cpu.endswith('n'):
                    cpu_usage += int(c_cpu.rstrip('n')) // 1_000_000
                elif c_cpu.endswith('m'):
                    cpu_usage += int(c_cpu.rstrip('m'))

                if c_mem.endswith('Ki'):
                    mem_usage += int(c_mem.rstrip('Ki')) // 1024
                elif c_mem.endswith('Mi'):
                    mem_usage += int(c_mem.rstrip('Mi'))

            usage_data.append((pod_namespace, pod_name, cpu_usage, mem_usage))

        usage_data.sort(key=lambda x: x[3], reverse=True)
        scope = f"'{ns}'" if ns else "all namespaces"
        output = f"**Top Resource Consumers in {scope}**:\n"

        if ns:
            output += "| Pod Name | Memory (Mi) | CPU (m) |\n|---|---|---|\n"
            for pod_ns, name, cpu, mem in usage_data[:15]:
                output += f"| {name} | {mem} Mi | {cpu} m |\n"
        else:
            output += "| Namespace | Pod Name | Memory (Mi) | CPU (m) |\n|---|---|---|---|\n"
            for pod_ns, name, cpu, mem in usage_data[:15]:
                output += f"| {pod_ns} | {name} | {mem} Mi | {cpu} m |\n"

        return output

    except Exception as e:
        return f"ERROR: Error fetching metrics: {str(e)}"


@tool
def analyze_pod_error(pod_name: str, namespace: str = ""):
    """
    Fetches logs and performs an AI analysis to find the root cause of a crash.
    Use this when a pod is in CrashLoopBackOff or Error state.

    Args:
        pod_name: Name of the pod to analyze
        namespace: Kubernetes namespace the pod lives in. Leave empty ("") to
            auto-detect it by searching ALL namespaces for this exact pod name.
    """
    try:
        v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]
        ns = kube_client.effective_namespace(namespace)

        if not ns:
            found = kube_client.find_pod_namespace(v1, pod_name)
            if found is None:
                return f"ERROR: Pod '{pod_name}' not found in any namespace."
            if isinstance(found, list):
                return (f"ERROR: Multiple pods named '{pod_name}' exist in namespaces: "
                         f"{', '.join(found)}. Specify which namespace to use.")
            ns = found

        logs = v1.read_namespaced_pod_log(name=pod_name, namespace=ns, tail_lines=100)

        prompt = f"""
Analyze these Kubernetes pod logs and identify the root cause of failure.
Be specific (e.g., "Database connection timeout", "Missing env var", "NullPointerException").

LOGS:
{logs}
"""

        analysis = llm.get_chat_model().invoke([HumanMessage(content=prompt)])
        return f"**AI Log Analysis for {pod_name} (namespace: {ns}):**\n\n{analysis.content}"

    except Exception as e:
        return f"ERROR: Error analyzing logs: {str(e)}"


@tool
def list_clusters():
    """
    Lists all Kubernetes clusters (contexts) available in the local kubeconfig,
    and indicates which one KubeBot is currently targeting.

    Use this tool when the user asks to list available clusters/contexts, or
    see which cluster is currently active.
    """
    try:
        names = kube_client.list_context_names()
        if not names:
            return "No clusters found in kubeconfig."

        effective = kube_client.resolve_context_name()
        lines = ["**Available Clusters:**\n"]
        for name in names:
            marker = " <- currently targeted by KubeBot" if name == effective else ""
            lines.append(f"- {name}{marker}")
        return "\n".join(lines)
    except config.ConfigException as e:
        return f"ERROR: Could not read kubeconfig: {e}"
    except Exception as e:
        return f"ERROR: {e}"


@tool
def switch_cluster(context_name: str):
    """
    Switches which Kubernetes cluster KubeBot targets for subsequent queries in
    this session. This is session-scoped only: it does NOT modify the user's
    shared kubeconfig file or its current-context, so it cannot affect any
    other terminal or kubectl session.

    Args:
        context_name: The exact context name to switch to (see 'list_clusters')

    Use this tool when the user asks to switch, change, or target a different cluster.
    """
    try:
        names = kube_client.list_context_names()
        if context_name not in names:
            return f"ERROR: Unknown context '{context_name}'. Available: {', '.join(names)}"

        # Verify the context is actually reachable before committing to it, and
        # reuse the verified client to warm the cache instead of discarding it.
        config.load_kube_config(context=context_name)
        core_v1 = client.CoreV1Api()
        core_v1.list_namespace(limit=1)
        kube_client.cache_clients(context_name, core_v1, client.AppsV1Api(), client.CustomObjectsApi())

        kube_client.set_current_context(context_name)
        warning = ""
        if any(tag in context_name.lower() for tag in ["prod", "prd"]):
            warning = "\n\nCAUTION: This looks like a PRODUCTION cluster. Double-check before running anything impactful."
        return f"SUCCESS: KubeBot is now targeting cluster '{context_name}' for this session.{warning}"
    except client.exceptions.ApiException as e:
        return f"ERROR: Connected to context but API call failed: {e.reason}"
    except Exception as e:
        return f"ERROR: Could not switch to '{context_name}': {e}"


@tool
def list_namespaces():
    """
    Lists all namespaces in the currently targeted cluster.
    Use this when the user asks what namespaces exist or wants an overview of the cluster layout.
    """
    try:
        v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]
        namespaces = v1.list_namespace()
        lines = [f"- {ns.metadata.name} (status: {ns.status.phase})" for ns in namespaces.items]
        return "**Namespaces:**\n" + "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


@tool
def list_nodes():
    """
    Lists all nodes in the currently targeted cluster with readiness and capacity.
    Use this when the user asks about node health, cluster capacity, or infra scaling.
    """
    try:
        v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]
        nodes = v1.list_node()
        lines = ["**Nodes:**\n"]
        for node in nodes.items:
            conditions = node.status.conditions or []
            ready = next((c.status for c in conditions if c.type == "Ready"), "Unknown")
            status = "Ready" if ready == "True" else "NotReady"
            capacity_cpu = node.status.capacity.get("cpu", "?")
            capacity_mem = node.status.capacity.get("memory", "?")
            lines.append(
                f"- {node.metadata.name} | Status: {status} | "
                f"CPU: {capacity_cpu} | Memory: {capacity_mem}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


@tool
def list_deployments(namespace: str = ""):
    """
    Lists deployments with their replica status (desired/ready/available).
    Use this when the user asks about deployment rollout status or replica counts.

    Args:
        namespace: Kubernetes namespace to inspect. Leave empty ("") to list
            deployments across ALL namespaces -- do not assume "default" for a
            cluster-wide request.
    """
    try:
        apps_v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["apps_v1"]
        ns = kube_client.effective_namespace(namespace)

        if ns:
            deployments = apps_v1.list_namespaced_deployment(namespace=ns).items
            scope = f"'{ns}'"
        else:
            deployments = apps_v1.list_deployment_for_all_namespaces().items
            scope = "all namespaces"

        if not deployments:
            return f"No deployments found in {scope}."

        lines = [f"**Deployments in {scope}:**\n"]
        for d in deployments:
            desired = d.spec.replicas
            ready = d.status.ready_replicas or 0
            available = d.status.available_replicas or 0
            name = d.metadata.name if ns else f"{d.metadata.namespace}/{d.metadata.name}"
            lines.append(
                f"- {name} | Desired: {desired} | Ready: {ready} | Available: {available}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


@tool
def get_recent_events(namespace: str = ""):
    """
    Fetches recent Warning-type Kubernetes events, useful for spotting scheduling
    failures, image pull errors, or probe failures that don't show up in pod status alone.

    Args:
        namespace: Restrict to a namespace, or leave empty for all namespaces.
    """
    try:
        v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]
        ns = kube_client.effective_namespace(namespace)
        if ns:
            events = v1.list_namespaced_event(namespace=ns)
        else:
            events = v1.list_event_for_all_namespaces()

        warning_events = [e for e in events.items if e.type == "Warning"]
        if not warning_events:
            return "No recent Warning events found."

        warning_events.sort(key=lambda e: e.last_timestamp or e.event_time or "", reverse=True)
        lines = ["**Recent Warning Events:**\n"]
        for e in warning_events[:15]:
            lines.append(
                f"- [{e.involved_object.kind}/{e.involved_object.name}] {e.reason}: {e.message}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


tools = [
    check_cluster_health,
    find_pods_by_keyword,
    list_all_pods,
    check_resource_usage,
    analyze_pod_error,
    get_pod_logs,
    consult_knowledge_base,
    list_clusters,
    switch_cluster,
    list_namespaces,
    list_nodes,
    list_deployments,
    get_recent_events,
]

# Friendly, user-facing labels shown in the activity panel while a tool runs.
TOOL_STATUS_LABELS = {
    "check_cluster_health": "Checking cluster health...",
    "find_pods_by_keyword": "Searching for matching pods...",
    "list_all_pods": "Listing pods...",
    "check_resource_usage": "Gathering CPU/memory metrics...",
    "analyze_pod_error": "Analyzing pod logs with AI...",
    "get_pod_logs": "Fetching pod logs...",
    "list_clusters": "Listing available clusters...",
    "switch_cluster": "Switching cluster...",
    "list_namespaces": "Listing namespaces...",
    "list_nodes": "Checking node status...",
    "list_deployments": "Checking deployment status...",
    "get_recent_events": "Fetching recent cluster events...",
    "consult_knowledge_base": "Searching knowledge base...",
}
