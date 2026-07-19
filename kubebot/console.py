"""Single shared rich Console instance used across the app."""

import warnings

from rich.console import Console

warnings.filterwarnings("ignore")

console = Console()
