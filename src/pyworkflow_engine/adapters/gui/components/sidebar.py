"""sidebar — menu de navigation latéral partagé."""

from __future__ import annotations

from nicegui import ui

# (icon, label, path)
_WORKFLOW_ITEMS = [
    ("dashboard", "Dashboard", "/"),
    ("work", "Jobs", "/jobs"),
    ("history", "Historique runs", "/runs"),
    ("article", "Logs", "/logs"),
]

_PIPELINE_ITEMS = [
    ("account_tree", "Pipelines", "/pipelines"),
    ("timeline", "Pipeline Runs", "/pipeline-runs"),
]

_AI_ITEMS = [
    ("smart_toy", "Agents IA", "/agents"),
    ("bolt", "Exécutions", "/executions"),
    ("chat", "Conversations", "/conversations"),
]

_MISC_ITEMS = [
    ("settings", "Paramètres", "/settings"),
]


def sidebar(active_path: str = "/") -> None:
    """Affiche la barre de navigation latérale.

    Args:
        active_path: Chemin de la page active (pour surligner l'entrée).
    """
    with ui.left_drawer(fixed=True).classes("bg-grey-9 text-white q-pa-sm"):
        # Logo / titre
        with ui.row().classes("items-center gap-2 q-pa-md q-mb-sm"):
            ui.icon("account_tree").classes("text-primary text-h4")
            with ui.column().classes("gap-0"):
                ui.label("PyWorkflow").classes("text-subtitle1 text-bold text-white")
                ui.label("Engine").classes("text-caption text-grey-4")

        ui.separator().classes("q-mb-sm")

        _nav_section("Workflow", _WORKFLOW_ITEMS, active_path)
        _nav_section("Pipelines", _PIPELINE_ITEMS, active_path, icon="account_tree", color="teal")
        _nav_section("Intelligence Artificielle", _AI_ITEMS, active_path, icon="smart_toy", color="deep-purple")

        ui.separator().classes("q-my-sm")

        _nav_section(None, _MISC_ITEMS, active_path)


def _nav_section(
    title: str | None,
    items: list[tuple[str, str, str]],
    active_path: str,
    icon: str = "folder",
    color: str = "primary",
) -> None:
    """Affiche un groupe de liens de navigation avec titre optionnel."""
    if title:
        with ui.row().classes("items-center gap-1 q-mt-sm q-mb-xs q-px-sm"):
            ui.icon(icon).classes(f"text-{color} text-caption")
            ui.label(title).classes(f"text-caption text-{color} text-bold")

    for nav_icon, label, path in items:
        is_active = active_path == path or (
            path != "/" and active_path.startswith(path)
        )
        btn_classes = "w-full text-left justify-start gap-2 " + (
            "bg-primary text-white" if is_active else "text-grey-3"
        )
        ui.button(
            label,
            icon=nav_icon,
            on_click=lambda p=path: ui.navigate.to(p),
        ).props("flat align=left no-caps").classes(btn_classes)
