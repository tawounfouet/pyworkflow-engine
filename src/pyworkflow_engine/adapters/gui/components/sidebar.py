"""sidebar — menu de navigation latéral partagé."""

from __future__ import annotations

from nicegui import ui


_NAV_ITEMS = [
    ("dashboard", "Dashboard", "/"),
    ("work", "Jobs", "/jobs"),
    ("history", "Historique", "/runs"),
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

        # Navigation items
        for icon, label, path in _NAV_ITEMS:
            is_active = active_path == path or (
                path != "/" and active_path.startswith(path)
            )
            btn_classes = "w-full text-left justify-start gap-2 " + (
                "bg-primary text-white" if is_active else "text-grey-3"
            )
            ui.button(
                label,
                icon=icon,
                on_click=lambda p=path: ui.navigate.to(p),
            ).props("flat align=left").classes(btn_classes)
