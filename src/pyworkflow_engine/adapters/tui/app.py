"""WorkflowTUI — interface terminal interactive pour PyWorkflow Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

if TYPE_CHECKING:
    from pyworkflow_engine.facade import WorkflowEngine

from pyworkflow_engine.adapters.tui.screens.dashboard import DashboardScreen


class WorkflowTUI(App[None]):
    """Application Textual pour la supervision interactive de workflows.

    Args:
        engine: Instance WorkflowEngine résolue par le loader CLI.

    Usage::

        from pyworkflow_engine.adapters.tui import WorkflowTUI
        tui = WorkflowTUI(engine)
        tui.run()
    """

    TITLE = "PyWorkflow Engine"
    SUB_TITLE = "Workflow Orchestration TUI"
    CSS_PATH = "styles/theme.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quitter", priority=True),
        Binding("d", "switch_to('dashboard')", "Dashboard"),
        Binding("j", "switch_to('jobs')", "Jobs"),
        Binding("h", "switch_to('history')", "Historique"),
        Binding("question_mark", "show_help", "Aide"),
        Binding("f5", "refresh_screen", "Rafraîchir", show=False),
        Binding("ctrl+r", "refresh_screen", "Rafraîchir", show=False),
    ]

    def __init__(self, engine: WorkflowEngine, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.engine = engine

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())

    def action_switch_to(self, screen_name: str) -> None:
        from pyworkflow_engine.adapters.tui.screens.dashboard import DashboardScreen
        from pyworkflow_engine.adapters.tui.screens.job_detail import JobListScreen
        from pyworkflow_engine.adapters.tui.screens.run_history import RunHistoryScreen

        screens: dict[str, type] = {
            "dashboard": DashboardScreen,
            "jobs": JobListScreen,
            "history": RunHistoryScreen,
        }
        screen_cls = screens.get(screen_name)
        if screen_cls:
            self.switch_screen(screen_cls())

    def action_show_help(self) -> None:
        help_text = (
            "[bold]Raccourcis clavier[/bold]\n\n"
            "  [cyan]d[/cyan]       Dashboard\n"
            "  [cyan]j[/cyan]       Liste des jobs\n"
            "  [cyan]h[/cyan]       Historique des runs\n"
            "  [cyan]Enter[/cyan]   Inspecter l'élément sélectionné\n"
            "  [cyan]r[/cyan]       Rafraîchir / Lancer\n"
            "  [cyan]c[/cyan]       Annuler le run sélectionné\n"
            "  [cyan]Shift+R[/cyan] Reprendre le run suspendu\n"
            "  [cyan]Escape[/cyan]  Retour au screen précédent\n"
            "  [cyan]F5[/cyan]      Forcer le rafraîchissement\n"
            "  [cyan]q[/cyan]       Quitter\n"
        )
        self.notify(help_text, title="Aide", timeout=10)

    def action_refresh_screen(self) -> None:
        screen = self.screen
        if hasattr(screen, "action_refresh"):
            screen.action_refresh()  # type: ignore[attr-defined]
