"""Vue Settings — configuration runtime de l'instance GUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nicegui import ui

from pyworkflow_engine.adapters.gui.components.toolbar import page_toolbar

if TYPE_CHECKING:
    from pyworkflow_engine.adapters.gui.config import GUIConfig
    from pyworkflow_engine.facade import WorkflowEngine


def build_settings(engine: WorkflowEngine, config: GUIConfig) -> None:
    """Construit la page Paramètres (/settings)."""
    page_toolbar("Paramètres", icon="settings", icon_color="grey-6")

    with ui.card().classes("w-full q-mb-md max-w-xl"):
        ui.label("Serveur").classes("text-subtitle1 text-bold q-mb-sm")
        _info_row("Hôte", config.host)
        _info_row("Port", str(config.port))
        _info_row("SQLite", config.db_path)
        _info_row("Titre", config.title)
        _info_row("Favicon", config.favicon)

    with ui.card().classes("w-full q-mb-md max-w-xl"):
        ui.label("Affichage").classes("text-subtitle1 text-bold q-mb-sm")
        with ui.row().classes("items-center gap-4 flex-wrap"):
            dark_toggle = ui.switch(
                "Mode sombre",
                value=config.dark_mode,
                on_change=lambda e: (
                    ui.dark_mode().enable() if e.value else ui.dark_mode().disable()
                ),
            )
            _ = dark_toggle  # referenced by on_change closure

        ui.separator().classes("q-my-sm")

        with ui.row().classes("items-center gap-2"):
            ui.label("Intervalle de rafraîchissement :").classes("text-body2")
            refresh_input = ui.number(
                value=config.refresh_interval,
                min=1.0,
                max=60.0,
                step=0.5,
                suffix="s",
            ).classes("w-24")

            def _apply_refresh() -> None:
                new_val = float(refresh_input.value or config.refresh_interval)
                config.refresh_interval = max(1.0, new_val)
                ui.notify(
                    f"Intervalle mis à jour : {config.refresh_interval} s",
                    type="positive",
                )

            ui.button("Appliquer", on_click=_apply_refresh).props("flat dense")

    with ui.card().classes("w-full q-mb-md max-w-xl"):
        ui.label("Moteur").classes("text-subtitle1 text-bold q-mb-sm")
        executors = engine.list_executors()
        if executors:
            for ex in executors:
                _info_row(
                    ex.name,
                    ex.executor_type.value if hasattr(ex, "executor_type") else str(ex),
                )
        else:
            ui.label("Aucun executor enregistré.").classes("text-caption text-grey-6")

    with ui.card().classes("w-full max-w-xl"):
        ui.label("À propos").classes("text-subtitle1 text-bold q-mb-sm")
        try:
            from pyworkflow_engine import __version__

            _info_row("Version", __version__)
        except ImportError:
            pass
        _info_row("GUI", "NiceGUI ≥ 2.0")
        _info_row("Documentation", "https://github.com/awf/pyworkflow-engine")


def _info_row(label: str, value: str) -> None:
    with ui.row().classes("items-start gap-2 q-mb-xs"):
        ui.label(label + " :").classes("text-caption text-grey-6 w-32")
        ui.label(value).classes("text-body2")
