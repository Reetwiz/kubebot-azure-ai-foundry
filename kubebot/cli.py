"""Application entry point: welcome banner, fast-path 'list X' shortcuts, and
the main REPL loop.
"""

import argparse
import re

from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from kubebot import __version__
from kubebot import config, kube_client, llm
from kubebot.agent import ActivityMonitor, append_turn, run_agent
from kubebot.console import console
from kubebot.prompts import welcome_text
from kubebot.rag import init as init_rag
from kubebot.slash_commands import handle_slash_command
from kubebot.tools import list_all_pods, list_clusters, list_deployments, list_namespaces, list_nodes

# Common, unambiguous "list X" questions don't need an LLM call to decide which
# tool to run -- they map directly to one tool. Matching them locally skips the
# round-trip(s) to the model entirely, making these near-instant and free, and
# avoids any risk of the model mis-scoping the namespace.
_FAST_PATH_PATTERNS = [
    (re.compile(r"^(list|show|get)\s+(all\s+)?namespaces?\s*\??\s*$", re.I),
        lambda m: list_namespaces.invoke({})),
    (re.compile(r"^(list|show|get)\s+(all\s+)?nodes?\s*\??\s*$", re.I),
        lambda m: list_nodes.invoke({})),
    (re.compile(r"^(list|show|get)\s+clusters?\s*\??\s*$", re.I),
        lambda m: list_clusters.invoke({})),
    (re.compile(r"^(list|show|get)\s+(all\s+)?pods?\s+(in|for|from)\s+(?P<ns>[\w.-]+)(\s+namespace)?\s*\??\s*$", re.I),
        lambda m: list_all_pods.invoke({"namespace": m.group("ns"), "status_filter": ""})),
    (re.compile(r"^(list|show|get)\s+(all\s+)?pods?(\s+(and|with)\s+status(es)?)?\s*\??\s*$", re.I),
        lambda m: list_all_pods.invoke({"namespace": "", "status_filter": ""})),
    (re.compile(r"^(list|show|get)\s+(all\s+)?deployments?\s+(in|for|from)\s+(?P<ns>[\w.-]+)(\s+namespace)?\s*\??\s*$", re.I),
        lambda m: list_deployments.invoke({"namespace": m.group("ns")})),
    (re.compile(r"^(list|show|get)\s+(all\s+)?deployments?\s*\??\s*$", re.I),
        lambda m: list_deployments.invoke({"namespace": ""})),
]


def _try_fast_path(user_input: str):
    """Return a direct tool result for common deterministic 'list X' questions,
    or None if nothing matched (caller should fall back to the LLM agent)."""
    text = user_input.strip()
    for pattern, handler in _FAST_PATH_PATTERNS:
        m = pattern.match(text)
        if m:
            return handler(m)
    return None


def print_welcome():
    """Display welcome banner with cluster info."""
    console.clear()

    try:
        # Warms the client cache for the default context too.
        cluster_name = kube_client.resolve_context_name()
        kube_client.get_clients(kube_client.CURRENT_CONTEXT)
    except Exception:
        cluster_name = "Unable to detect cluster"

    mode_label = "Development" if config.DEV_MODE else "Production"

    # Render as Markdown (not a raw string) so **bold**/bullets actually render
    # instead of showing literal asterisks inside the panel.
    text = welcome_text(cluster_name, mode_label, llm.current_deployment_name())
    console.print(Panel(Markdown(text), style="bold blue", expand=False))


def main():
    """Main application loop."""
    parser = argparse.ArgumentParser(description="Read-only Kubernetes troubleshooting assistant")
    parser.add_argument("--version", action="version", version=f"KubeBot {__version__}")
    parser.parse_args()

    config.configure_provider()
    try:
        llm.init()
        init_rag()
    except Exception as error:
        if not config.offer_ollama_fallback(error):
            provider = llm.provider_name()
            console.print(f"[bold red]{provider} could not start:[/bold red] {error}")
            if config.LLM_PROVIDER == "ollama":
                console.print(
                    "[yellow]Start Ollama and pull the configured chat and embedding models, then try again.[/yellow]"
                )
            raise SystemExit(1) from None
        try:
            llm.init()
            init_rag()
        except Exception as fallback_error:
            console.print(f"[bold red]Ollama could not start:[/bold red] {fallback_error}")
            console.print(
                "[yellow]Start Ollama and pull the configured chat and embedding models, then try again.[/yellow]"
            )
            raise SystemExit(1) from None

    print_welcome()

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]You[/bold green]")

            if user_input.lower() in ["exit", "quit", "bye"]:
                console.print("[bold blue]Goodbye! Happy troubleshooting![/bold blue]")
                break

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                if not handle_slash_command(user_input):
                    console.print(f"[yellow]Unknown command: {user_input}. Type /help for options.[/yellow]")
                continue

            fast_result = _try_fast_path(user_input)
            if fast_result is not None:
                if config.DEV_MODE:
                    console.print("[dim](answered locally -- no LLM call needed)[/dim]")
                console.print("\n[bold purple]KubeBot:[/bold purple]")
                console.print(Markdown(fast_result))
                # Still recorded in history so follow-up questions have context.
                append_turn(user_input, fast_result)
                continue

            with ActivityMonitor(console) as monitor:
                response = run_agent(user_input, monitor=monitor)

            # Display response
            console.print("\n[bold purple]KubeBot:[/bold purple]")
            console.print(Markdown(response))

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Session interrupted.[/bold yellow]")
            break
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}")
            if config.DEV_MODE:
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        console.print(f"\n[bold red]Fatal Error:[/bold red] {e}")
