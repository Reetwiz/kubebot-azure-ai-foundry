"""Interactive fuzzy-find picker for cluster/namespace selection, similar to
`fzf`: type to filter, arrow keys to move, Enter to select, Esc/Ctrl-C to
cancel. Used by '/switch' and '/namespace pick' when no exact name is given.
"""

from InquirerPy import inquirer
from InquirerPy.base.control import Choice


def fuzzy_pick(choices, message: str, current: str = None):
    """Show a fuzzy-find prompt over `choices` (list[str]) and return the
    selected string, or None if the user cancelled (Ctrl-C/Esc) or the list
    was empty.
    """
    if not choices:
        return None

    options = [
        Choice(value=c, name=f"{c} (current)" if c == current else c)
        for c in choices
    ]

    try:
        return inquirer.fuzzy(
            message=message,
            choices=options,
            max_height="70%",
            border=True,
        ).execute()
    except KeyboardInterrupt:
        return None
