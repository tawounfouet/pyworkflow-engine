"""toolbar — barre de titre de page avec bouton retour optionnel."""

from __future__ import annotations

from nicegui import ui


def page_toolbar(
    title: str,
    icon: str = "circle",
    icon_color: str = "primary",
    back_url: str | None = None,
    subtitle: str | None = None,
) -> None:
    """Affiche une barre de titre standardisée pour une vue.

    Args:
        title: Titre principal affiché.
        icon: Nom d'icône Material Design.
        icon_color: Classe de couleur Quasar pour l'icône.
        back_url: Si fourni, affiche un bouton retour vers cette URL.
        subtitle: Sous-titre optionnel (affiché en petit).
    """
    with ui.row().classes("items-center gap-2 q-mb-md w-full"):
        if back_url:
            ui.button(
                icon="arrow_back",
                on_click=lambda: ui.navigate.to(back_url),
            ).props("flat round dense")
        ui.icon(icon).classes(f"text-{icon_color} text-h5")
        with ui.column().classes("gap-0"):
            ui.label(title).classes("text-h5 text-bold leading-tight")
            if subtitle:
                ui.label(subtitle).classes("text-caption text-grey-6")
