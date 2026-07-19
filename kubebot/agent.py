"""The tool-calling agent loop, conversation history management, and the
transient 'ActivityMonitor' scrolling status panel shown while it works.
"""

from collections import deque

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from rich.live import Live
from rich.panel import Panel

from kubebot import config, llm
from kubebot.prompts import SYSTEM_PROMPT
from kubebot.tools import TOOL_STATUS_LABELS, tools

conversation_history = []


def _trim_history():
    """Keep only the most recent MAX_TURNS turns, cutting on HumanMessage boundaries
    so tool_call/ToolMessage pairs are never split apart."""
    global conversation_history
    turn_starts = [i for i, m in enumerate(conversation_history) if isinstance(m, HumanMessage)]
    if len(turn_starts) > config.MAX_TURNS:
        cutoff = turn_starts[-config.MAX_TURNS]
        conversation_history = conversation_history[cutoff:]


def clear_history():
    global conversation_history
    conversation_history = []


def append_turn(user_input: str, response_text: str):
    """Record a locally-answered (non-LLM) turn so later LLM turns retain context."""
    conversation_history.append(HumanMessage(content=user_input))
    conversation_history.append(AIMessage(content=response_text))
    _trim_history()


class ActivityMonitor:
    """A small, cropped, scrolling status panel (similar to Copilot Chat's
    collapsed 'thinking' box) that shows the last few steps the agent has
    taken (thinking, which tool is running, and its outcome) while it works.
    The panel is transient: it disappears once the final answer is ready.
    """

    def __init__(self, console, max_lines: int = 8):
        self.console = console
        self.max_lines = max_lines
        self.lines = deque(maxlen=max_lines)
        self._live = None

    def _render(self):
        body = "\n".join(self.lines) if self.lines else "[dim]Starting...[/dim]"
        return Panel(
            body,
            title="[bold cyan]KubeBot is working[/bold cyan]",
            border_style="cyan",
            expand=False,
        )

    def __enter__(self):
        self._live = Live(self._render(), console=self.console, refresh_per_second=12, transient=True)
        self._live.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._live.stop()

    def log(self, message: str):
        self.lines.append(message)
        if self._live is not None:
            self._live.update(self._render())


def run_agent(user_input: str, monitor: "ActivityMonitor" = None) -> str:
    """
    Run the agent with the user input and return the response.

    If `monitor` (an ActivityMonitor) is provided, it is fed a scrolling log of
    what the agent is doing (thinking / which tool is running / outcome) so
    the user has visibility into long-running turns, similar to Copilot's
    collapsed 'thinking' panel.
    """
    global conversation_history

    conversation_history.append(HumanMessage(content=user_input))
    _trim_history()

    # Bound fresh each call (cheap, no network I/O) so a '/model' switch made
    # mid-session takes effect on the very next turn.
    llm_with_tools = llm.get_chat_model().bind_tools(tools)

    max_iterations = 50
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        if monitor is not None and config.DEV_MODE:
            monitor.log("[dim]Thinking...[/dim]" if iteration == 1 else "[dim]Reviewing tool results...[/dim]")

        # System prompt is prepended on every call (not stored in history) so it
        # always reflects the latest directives without bloating saved context.
        response = llm_with_tools.invoke([SystemMessage(content=SYSTEM_PROMPT)] + conversation_history)

        if hasattr(response, 'tool_calls') and response.tool_calls:
            conversation_history.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                tool_args = tool_call['args']

                if monitor is not None:
                    label = TOOL_STATUS_LABELS.get(tool_name, f"Running {tool_name}...")
                    if config.DEV_MODE:
                        args_preview = ", ".join(f"{k}={v}" for k, v in tool_args.items())
                        if args_preview:
                            if len(args_preview) > 60:
                                args_preview = args_preview[:60] + "…"
                            monitor.log(f"[bold cyan]▸[/bold cyan] {label} [dim]({args_preview})[/dim]")
                        else:
                            monitor.log(f"[bold cyan]▸[/bold cyan] {label}")
                    else:
                        monitor.log(f"[bold cyan]▸[/bold cyan] {label}")

                tool_fn = next((t for t in tools if t.name == tool_name), None)
                if tool_fn is None:
                    tool_result = f"ERROR: Unknown tool '{tool_name}' requested."
                    if monitor is not None:
                        monitor.log(f"[bold red]✗[/bold red] Unknown tool '{tool_name}'")
                else:
                    try:
                        tool_result = tool_fn.invoke(tool_args)
                        if monitor is not None:
                            if config.DEV_MODE:
                                monitor.log(f"[bold green]✓[/bold green] {tool_name} done ({len(str(tool_result))} chars)")
                            else:
                                monitor.log(f"[bold green]✓[/bold green] {tool_name} done")
                    except Exception as e:
                        tool_result = f"ERROR: Tool '{tool_name}' failed: {e}"
                        if monitor is not None:
                            monitor.log(f"[bold red]✗[/bold red] {tool_name} failed: {e}")

                tool_message = ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_call['id']
                )
                conversation_history.append(tool_message)
        else:
            conversation_history.append(response)
            return response.content

    return "Maximum iterations reached. Please try rephrasing your question."
