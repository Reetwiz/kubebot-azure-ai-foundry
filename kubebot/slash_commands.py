"""Local '/' command palette, handled before hitting the LLM (no tokens/latency)."""

import shlex
import subprocess

from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from kubebot import agent, kube_client, llm
from kubebot.console import console
from kubebot.fuzzy import fuzzy_pick
from kubebot.prompts import SLASH_COMMANDS_HELP
from kubebot.tools import switch_cluster, tools

# kubectl verbs allowed through '/command'. Deliberately excludes anything that
# mutates cluster state (apply/delete/edit/exec/patch/scale/rollout/cp/...).
READONLY_KUBECTL_VERBS = {
    "get", "describe", "logs", "top", "explain",
    "version", "api-resources", "api-versions", "cluster-info",
}

# Flags that could redirect kubectl to a different cluster/kubeconfig or
# impersonate another identity -- always stripped so '/command' can never be
# used to escalate privileges or silently leave the session's own context.
BLOCKED_KUBECTL_FLAGS = ("--context", "--kubeconfig", "--as", "--as-group", "--token", "--user", "--cluster")


def _run_readonly_kubectl(args_str: str) -> str:
    """Run a strictly read-only kubectl command against the session's current
    context. Only the READONLY_KUBECTL_VERBS allow-list is permitted; Secrets
    are always blocked to avoid leaking credentials through the chat interface;
    context/kubeconfig/impersonation flags are stripped and replaced with the
    session's own context; and the process is run via argv (no shell=True), so
    shell metacharacters in the input can't be interpreted.
    """
    try:
        tokens = shlex.split(args_str)
    except ValueError as e:
        return f"ERROR: Could not parse command: {e}"

    if tokens and tokens[0] == "kubectl":
        tokens = tokens[1:]

    if not tokens:
        return "ERROR: No command given. Example: /command get pods -n dev-billing"

    verb = tokens[0]
    if verb not in READONLY_KUBECTL_VERBS:
        return (f"ERROR: '{verb}' is not allowed. KubeBot only runs read-only kubectl "
                f"commands: {', '.join(sorted(READONLY_KUBECTL_VERBS))}.")

    for blocked in BLOCKED_KUBECTL_FLAGS:
        if any(t == blocked or t.startswith(blocked + "=") for t in tokens):
            return f"ERROR: '{blocked}' is not allowed -- KubeBot always targets its own session cluster/context."

    if verb in ("get", "describe"):
        resource_arg = next((t for t in tokens[1:] if not t.startswith("-")), "")
        resource_type = resource_arg.split("/")[0].lower().rstrip("s")
        if resource_type == "secret":
            return "ERROR: Reading Secrets via /command is blocked to avoid leaking credentials through chat."

    context_name = kube_client.resolve_context_name()
    full_cmd = ["kubectl", "--context", context_name] + tokens

    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=20, shell=False)
    except FileNotFoundError:
        return "ERROR: kubectl binary not found on PATH."
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 20s."

    output = result.stdout if result.returncode == 0 else (result.stderr or result.stdout)
    output = output.strip()
    if len(output) > 4000:
        output = output[:4000] + "\n... [truncated]"
    if not output:
        return "(no output)"
    prefix = "" if result.returncode == 0 else f"ERROR (exit {result.returncode}): "
    return f"{prefix}```\n{output}\n```"


def handle_slash_command(cmd: str) -> bool:
    """Handle a local '/' command without involving the LLM. Returns True if handled."""
    parts = cmd.strip().split(maxsplit=1)
    name = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if name in ("/help", "/?"):
        console.print(Panel(Markdown(SLASH_COMMANDS_HELP), title="Help", border_style="blue", expand=False))

    elif name in ("/clusters", "/contexts"):
        try:
            names = kube_client.list_context_names()
            effective = kube_client.resolve_context_name()
            table = Table(title="Available Clusters", border_style="blue")
            table.add_column("Context")
            table.add_column("Active")
            for name_ in names:
                is_active = "yes" if name_ == effective else ""
                table.add_row(name_, is_active)
            console.print(table)
        except Exception as e:
            console.print(f"[bold red]Error listing clusters:[/bold red] {e}")

    elif name == "/switch":
        if not arg:
            # No name given -- fuzzy-find over available contexts (fzf-like UX).
            try:
                names = kube_client.list_context_names()
            except Exception as e:
                console.print(f"[bold red]Error listing clusters:[/bold red] {e}")
                return True
            picked = fuzzy_pick(names, "Switch cluster:", current=kube_client.resolve_context_name())
            if picked is None:
                console.print("[yellow]Cancelled.[/yellow]")
            else:
                console.print(Markdown(switch_cluster.invoke({"context_name": picked})))
        else:
            console.print(Markdown(switch_cluster.invoke({"context_name": arg})))

    elif name == "/context":
        console.print(f"[bold]Currently targeting:[/bold] {kube_client.resolve_context_name()}")

    elif name in ("/namespace", "/ns"):
        if not arg:
            current = kube_client.CURRENT_NAMESPACE or "(none set -- tools default to ALL namespaces)"
            console.print(f"[bold]Pinned namespace:[/bold] {current}")
            console.print("[dim]Use '/namespace pick' to fuzzy-search live namespaces.[/dim]")
        elif arg.lower() in ("clear", "all", "none"):
            kube_client.set_current_namespace(None)
            console.print("[green]Namespace pin cleared -- tools now default to ALL namespaces.[/green]")
        elif arg.lower() in ("pick", "fzf", "-"):
            try:
                v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]
                names = [ns.metadata.name for ns in v1.list_namespace().items]
            except Exception as e:
                console.print(f"[bold red]Error listing namespaces:[/bold red] {e}")
                return True
            picked = fuzzy_pick(names, "Pin namespace:", current=kube_client.CURRENT_NAMESPACE)
            if picked is None:
                console.print("[yellow]Cancelled.[/yellow]")
            else:
                kube_client.set_current_namespace(picked)
                console.print(f"[green]Pinned default namespace to '{picked}' for this session.[/green]")
        else:
            try:
                v1 = kube_client.get_clients(kube_client.CURRENT_CONTEXT)["core_v1"]
                names = [ns.metadata.name for ns in v1.list_namespace().items]
                if arg not in names:
                    console.print(f"[yellow]WARNING: '{arg}' was not found in the current cluster's namespaces. Pinning anyway.[/yellow]")
                kube_client.set_current_namespace(arg)
                console.print(f"[green]Pinned default namespace to '{arg}' for this session.[/green]")
            except Exception as e:
                console.print(f"[bold red]Error pinning namespace:[/bold red] {e}")

    elif name == "/model":
        options = llm.available_models()
        if not arg:
            lines = [f"**Active model deployment:** `{llm.current_deployment_name()}`\n", "**Available:**"]
            for label, deployment in options.items():
                marker = " (active)" if deployment == llm.current_deployment_name() else ""
                lines.append(f"- `{label}` -> `{deployment}`{marker}")
            console.print(Markdown("\n".join(lines)))
        else:
            try:
                with console.status(f"[cyan]Verifying deployment '{arg}'...[/cyan]"):
                    resolved = llm.switch_model(arg)
                console.print(f"[green]SUCCESS:[/green] Switched to deployment '{resolved}'.")
            except ValueError as e:
                console.print(f"[bold red]ERROR:[/bold red] {e}")

    elif name in ("/command", "/kubectl"):
        if not arg:
            console.print("[yellow]Usage: /command <kubectl-args> (read-only verbs only: "
                          "get/describe/logs/top/explain/version/api-resources/api-versions/cluster-info)[/yellow]")
        else:
            console.print(Markdown(_run_readonly_kubectl(arg)))

    elif name == "/tools":
        table = Table(title="Available Tools", border_style="blue")
        table.add_column("Tool")
        table.add_column("Purpose")
        for t in tools:
            first_line = next((l.strip() for l in t.description.splitlines() if l.strip()), "")
            table.add_row(t.name, first_line)
        console.print(table)

    elif name == "/clear":
        agent.clear_history()
        console.print("[green]Conversation history cleared.[/green]")

    else:
        return False

    return True
