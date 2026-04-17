"""
Commandes de gestion des agents IA : list, inspect, run, chat, history, sync.

Architecture : ADR-019 (Phase 3 & 4)
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pyworkflow_engine.adapters.cli.errors import error_handler
from pyworkflow_engine.models.ai.types import MessageRole

app = typer.Typer(
    name="agent",
    help="Gérer et exécuter les agents IA (list, inspect, run, chat).",
    no_args_is_help=True,
)
console = Console()


def _role_style(role: str) -> str:
    """Applique un style Rich au rôle de l'agent."""
    styles = {
        "assistant": "[bold green]assistant[/]",
        "researcher": "[bold blue]researcher[/]",
        "coder": "[bold yellow]coder[/]",
        "analyst": "[bold magenta]analyst[/]",
        "orchestrator": "[bold cyan]orchestrator[/]",
        "reviewer": "[bold red]reviewer[/]",
        "custom": "[dim]custom[/]",
    }
    return styles.get(role, f"[dim]{role}[/]")


@app.command("list")
@error_handler
def list_agents(
    ctx: typer.Context,
    role: Optional[str] = typer.Option(
        None,
        "--role",
        "-r",
        help="Filtrer par rôle (assistant, researcher, coder, analyst, orchestrator).",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        "-t",
        help="Filtrer par tag.",
    ),
) -> None:
    """Liste tous les agents IA déclarés dans le manifest."""
    from agents.shared.loader import AgentLoadError, load_all_agents, load_manifest

    output_format = ctx.obj.get("format", "table") if ctx.obj else "table"

    try:
        entries = load_manifest()
        agents = load_all_agents()
    except (FileNotFoundError, AgentLoadError) as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1) from exc

    # Filtrage
    filtered = list(zip(entries, agents))
    if role:
        filtered = [(e, a) for e, a in filtered if a.role.value == role]
    if tag:
        filtered = [(e, a) for e, a in filtered if tag in e.get("tags", [])]

    if not filtered:
        console.print("[dim]Aucun agent trouvé.[/dim]")
        return

    if output_format == "json":
        import json

        data = [
            {
                "name": a.name,
                "slug": a.slug,
                "role": a.role.value,
                "description": a.description,
                "provider_id": a.provider_id,
                "model": a.model,
                "tools": len(a.tool_ids),
                "skills": len(a.skill_ids),
                "temperature": a.config.temperature,
                "tags": e.get("tags", []),
            }
            for e, a in filtered
        ]
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        table = Table(title="🤖  Agents IA", show_lines=True, expand=False)
        table.add_column("Slug", style="bold cyan", no_wrap=True)
        table.add_column("Nom", style="white")
        table.add_column("Rôle", justify="center")
        table.add_column("Provider", style="dim")
        table.add_column("Tools", justify="right", style="magenta")
        table.add_column("Temp.", justify="right", style="dim")
        table.add_column("Tags", style="dim")

        for entry, agent in filtered:
            temp = (
                str(agent.config.temperature)
                if agent.config.temperature is not None
                else "—"
            )
            tags = ", ".join(entry.get("tags", []))
            table.add_row(
                agent.slug,
                agent.name,
                _role_style(agent.role.value),
                agent.provider_id,
                str(len(agent.tool_ids)),
                temp,
                tags,
            )

        console.print(table)
        console.print(f"\n[dim]{len(filtered)} agent(s) trouvé(s).[/dim]")


@app.command("inspect")
@error_handler
def inspect_agent(
    ctx: typer.Context,
    slug: str = typer.Argument(help="Slug de l'agent à inspecter"),
) -> None:
    """Affiche la configuration détaillée d'un agent IA."""
    from agents.shared.loader import AgentLoadError, load_agent_by_slug

    output_format = ctx.obj.get("format", "table") if ctx.obj else "table"

    try:
        agent = load_agent_by_slug(slug)
    except (FileNotFoundError, AgentLoadError) as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1) from exc

    if output_format == "json":
        import json

        typer.echo(
            json.dumps(agent.model_dump(mode="json"), indent=2, ensure_ascii=False)
        )
    else:
        # Header
        console.print(
            Panel(
                f"[bold]{agent.name}[/bold]  [dim]({agent.slug})[/dim]\n\n"
                f"{agent.description}",
                title=f"🤖 Agent — {_role_style(agent.role.value)}",
                expand=False,
            )
        )

        # Configuration
        cfg_table = Table(title="⚙️  Configuration", show_lines=True, expand=False)
        cfg_table.add_column("Paramètre", style="cyan", no_wrap=True)
        cfg_table.add_column("Valeur")

        cfg_table.add_row("provider_id", agent.provider_id)
        cfg_table.add_row("model", agent.model or "[dim]default du provider[/dim]")
        cfg_table.add_row(
            "temperature",
            (
                str(agent.config.temperature)
                if agent.config.temperature is not None
                else "[dim]None (provider default)[/dim]"
            ),
        )
        cfg_table.add_row("max_iterations", str(agent.config.max_iterations))
        cfg_table.add_row("max_tokens_per_run", str(agent.config.max_tokens_per_run))
        cfg_table.add_row("enable_memory", "✅" if agent.config.enable_memory else "❌")
        cfg_table.add_row("enable_tools", "✅" if agent.config.enable_tools else "❌")
        cfg_table.add_row("enable_rag", "✅" if agent.config.enable_rag else "❌")
        cfg_table.add_row(
            "retry_on_failure", "✅" if agent.config.retry_on_failure else "❌"
        )
        cfg_table.add_row("max_retries", str(agent.config.max_retries))

        console.print(cfg_table)

        # Tools, Skills, Knowledge bases
        if agent.tool_ids:
            console.print(
                f"\n[bold]🔧 Tools[/bold] ({len(agent.tool_ids)}): {', '.join(agent.tool_ids)}"
            )
        if agent.skill_ids:
            console.print(
                f"[bold]🎯 Skills[/bold] ({len(agent.skill_ids)}): {', '.join(agent.skill_ids)}"
            )
        if agent.knowledge_base_ids:
            console.print(
                f"[bold]📚 Knowledge bases[/bold] ({len(agent.knowledge_base_ids)}): {', '.join(agent.knowledge_base_ids)}"
            )

        # System prompt (truncated)
        prompt = agent.system_prompt
        if prompt:
            if len(prompt) > 300:
                prompt = prompt[:300] + "…"
            console.print(
                Panel(
                    prompt, title="💬 System Prompt", expand=False, border_style="dim"
                )
            )

        if agent.welcome_message:
            console.print(f"\n[dim]Welcome:[/dim] {agent.welcome_message}")

        console.print()


@app.command("run")
@error_handler
def run_agent(
    ctx: typer.Context,
    slug: str = typer.Argument(help="Slug de l'agent à exécuter"),
    message: str = typer.Argument(help="Message à envoyer à l'agent"),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Override du modèle LLM (ex: gpt-4o-mini).",
    ),
    temperature: Optional[float] = typer.Option(
        None,
        "--temperature",
        "-T",
        help="Override de la température (0.0–2.0).",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Afficher les métriques (tokens, temps de réponse).",
    ),
    no_persist: bool = typer.Option(
        False,
        "--no-persist",
        help="Désactiver la persistance dans workflow.db.",
    ),
) -> None:
    """Exécute un agent en mode one-shot (une question → une réponse)."""
    from jobs.shared.logging import configure_platform_logging

    from agents.shared.loader import AgentLoadError, load_agent_by_slug
    from agents.shared.runner import AgentRunner, AgentRunnerError

    configure_platform_logging()

    try:
        agent = load_agent_by_slug(slug)
    except (FileNotFoundError, AgentLoadError) as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1) from exc

    try:
        runner = AgentRunner(
            agent, model=model, verbose=verbose, persist=not no_persist
        )
    except AgentRunnerError as exc:
        console.print(f"[bold red]✗ Provider error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        f"[dim]🤖 {agent.name} ({runner.model}) — température: "
        f"{temperature if temperature is not None else agent.config.temperature or '0.7'}[/dim]\n"
    )

    try:
        kwargs: dict[str, object] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        with console.status("[bold cyan]Réflexion…[/bold cyan]"):
            response = runner.ask(message, **kwargs)
    except AgentRunnerError as exc:
        console.print(f"[bold red]✗ Erreur LLM:[/bold red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        # Clôturer le run one-shot dans tous les cas
        runner.finish()

    # Afficher la réponse
    from rich.markdown import Markdown

    console.print(Markdown(response.content))

    # Métriques
    if verbose and response.usage:
        u = response.usage
        rt = f"{response.response_time_ms:.0f}ms" if response.response_time_ms else "—"
        console.print(
            f"\n[dim]⚡ {u.total_tokens} tokens "
            f"(prompt: {u.prompt_tokens}, completion: {u.completion_tokens}) "
            f"— {rt} — modèle: {response.model}[/dim]"
        )


@app.command("chat")
@error_handler
def chat_agent(
    ctx: typer.Context,
    slug: str = typer.Argument(help="Slug de l'agent pour la session interactive"),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Override du modèle LLM (ex: gpt-4o-mini).",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Afficher les métriques après chaque réponse.",
    ),
    no_persist: bool = typer.Option(
        False,
        "--no-persist",
        help="Désactiver la persistance dans workflow.db.",
    ),
) -> None:
    """Lance une session de chat interactive (REPL) avec un agent."""
    from jobs.shared.logging import configure_platform_logging

    from agents.shared.loader import AgentLoadError, load_agent_by_slug
    from agents.shared.runner import AgentRunner, AgentRunnerError

    configure_platform_logging()

    try:
        agent = load_agent_by_slug(slug)
    except (FileNotFoundError, AgentLoadError) as exc:
        console.print(f"[bold red]✗[/bold red] {exc}")
        raise typer.Exit(1) from exc

    try:
        runner = AgentRunner(
            agent, model=model, verbose=verbose, persist=not no_persist
        )
    except AgentRunnerError as exc:
        console.print(f"[bold red]✗ Provider error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    runner.repl()  # repl() appelle finish() dans son finally


@app.command("history")
@error_handler
def history_agent(
    ctx: typer.Context,
    slug: Optional[str] = typer.Argument(
        None, help="Slug de l'agent (optionnel, tous si absent)"
    ),
    limit: int = typer.Option(
        20, "--limit", "-n", help="Nombre de conversations à afficher."
    ),
    messages: bool = typer.Option(
        False,
        "--messages",
        "-m",
        help="Afficher aussi les messages de chaque conversation.",
    ),
) -> None:
    """Affiche l'historique des conversations d'agents depuis workflow.db."""
    import os
    from pathlib import Path

    from pyworkflow_engine.adapters.ai.storage.sqlite import SQLiteAIStorage

    db_path = os.environ.get("PYWORKFLOW_DB", "workflow.db")
    db_path = str(Path(db_path).expanduser().resolve())

    try:
        storage = SQLiteAIStorage(db_path)
    except Exception as exc:
        console.print(
            f"[bold red]✗[/bold red] Impossible d'ouvrir workflow.db : {exc}\n"
            "[dim]Vérifiez que le fichier existe et est accessible.[/dim]"
        )
        raise typer.Exit(1) from exc

    # Resolve agent_id from slug if provided
    agent_id: str | None = None
    if slug:
        agent = storage.get_agent_by_slug(slug)
        if agent:
            agent_id = agent.id
        else:
            console.print(
                f"[bold red]✗[/bold red] Agent [cyan]{slug}[/cyan] introuvable.\n"
                "[dim]Lancez d'abord une commande agent (run/chat) ou 'agent sync'.[/dim]"
            )
            raise typer.Exit(1)

    conversations = storage.list_conversations(agent_id=agent_id)
    # Sort by created_at desc and limit
    conversations.sort(key=lambda c: c.created_at, reverse=True)
    conversations = conversations[:limit]

    if not conversations:
        console.print("[dim]Aucune conversation trouvée.[/dim]")
        return

    output_format = ctx.obj.get("format", "table") if ctx.obj else "table"

    if output_format == "json":
        import json

        data = [c.model_dump(mode="json") for c in conversations]
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return

    _status_style = {
        "active": "[bold yellow]⏳ active[/]",
        "completed": "[bold green]✅ completed[/]",
        "archived": "[bold red]📦 archived[/]",
    }

    table = Table(
        title=f"🤖  Historique des conversations{f' — {slug}' if slug else ''}",
        show_lines=False,
        header_style="bold",
        expand=False,
    )
    table.add_column("Conv ID", style="dim", no_wrap=True)
    table.add_column("Agent", style="bold cyan", no_wrap=True)
    table.add_column("Mode", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Msgs", justify="right", style="magenta")
    table.add_column("Tokens", justify="right", style="yellow")
    table.add_column("Créé le", style="dim", no_wrap=True)

    for conv in conversations:
        conv_id_short = conv.id[:8]
        status_txt = _status_style.get(conv.status.value, conv.status.value)
        tokens = str(conv.total_tokens or 0)
        mode = conv.metadata.get("mode", "—") if conv.metadata else "—"

        # Resolve agent slug from agent_id
        agent_slug = "—"
        if conv.agent_id:
            ag = storage.get_agent(conv.agent_id)
            if ag:
                agent_slug = ag.slug

        try:
            from datetime import datetime

            start_fmt = conv.created_at.strftime("%d/%m %H:%M")
        except (ValueError, AttributeError):
            start_fmt = str(conv.created_at)[:16]

        table.add_row(
            conv_id_short,
            agent_slug,
            mode,
            status_txt,
            str(conv.message_count or 0),
            tokens,
            start_fmt,
        )

    console.print(table)
    console.print(f"\n[dim]{len(conversations)} conversation(s) trouvée(s).[/dim]")

    # Détail des messages si demandé
    if messages:
        for conv in conversations:
            msgs = storage.get_messages(conv.id)
            if not msgs:
                continue

            agent_slug = "—"
            if conv.agent_id:
                ag = storage.get_agent(conv.agent_id)
                if ag:
                    agent_slug = ag.slug

            console.print(
                Panel(
                    "\n".join(
                        f"[{'green' if m.role == MessageRole.USER else 'cyan'}]"
                        f"[{m.role.value.upper()}][/] "
                        f"{m.content[:120]}{'…' if len(m.content) > 120 else ''}"
                        for m in msgs
                        if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
                    ),
                    title=f"Messages — {agent_slug} / {conv.id[:8]}…",
                    expand=False,
                    border_style="dim",
                )
            )


@app.command("sync")
@error_handler
def sync_agents(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Affiche ce qui serait synchronisé sans rien écrire en base.",
    ),
    show: bool = typer.Option(
        False,
        "--show",
        "-s",
        help="Affiche le tableau des agents persistés après la sync.",
    ),
) -> None:
    """Synchronise le catalogue d'agents Python → workflow.db (ai_agents).

    Lit chaque agent déclaré dans agents/manifest.yaml + modules Python,
    puis effectue un UPSERT dans la table ai_agents (et crée les entrées
    manquantes dans ai_providers) via SQLiteAIStorage.

    Idempotent : peut être rejoué sans risque à chaque déploiement.
    """
    import os
    from pathlib import Path

    from agents.shared.loader import AgentLoadError, load_all_agents

    # ── Dry-run : juste charger et afficher ──────────────────────────────────
    if dry_run:
        try:
            agents = load_all_agents()
        except (FileNotFoundError, AgentLoadError) as exc:
            console.print(f"[bold red]✗[/bold red] {exc}")
            raise typer.Exit(1) from exc

        table = Table(
            title="🔍  Dry-run — agents à synchroniser",
            show_lines=False,
            header_style="bold",
        )
        table.add_column("Slug", style="bold cyan", no_wrap=True)
        table.add_column("Nom")
        table.add_column("Rôle", justify="center")
        table.add_column("Provider", style="dim")
        table.add_column("Modèle", style="dim")
        table.add_column("Tools", justify="right", style="magenta")

        for a in agents:
            table.add_row(
                a.slug,
                a.name,
                _role_style(a.role.value),
                a.provider_id,
                a.model or "[dim]default[/dim]",
                str(len(a.tool_ids)),
            )

        console.print(table)
        console.print(
            f"\n[dim]{len(agents)} agent(s) seraient synchronisés "
            "(--dry-run, rien n'a été écrit)[/dim]"
        )
        return

    # ── Sync réelle via SQLiteAIStorage ───────────────────────────────────
    from pyworkflow_engine.adapters.ai.storage.sqlite import SQLiteAIStorage

    db_path = os.environ.get("PYWORKFLOW_DB", "workflow.db")
    db_path = str(Path(db_path).expanduser().resolve())

    try:
        storage = SQLiteAIStorage(db_path)
    except Exception as exc:
        console.print(
            f"[bold red]✗[/bold red] workflow.db introuvable ou inaccessible : {exc}\n"
            "[dim]Lancez d'abord une commande pyworkflow pour initialiser la DB.[/dim]"
        )
        raise typer.Exit(1) from exc

    try:
        agents = load_all_agents()
    except (AgentLoadError, FileNotFoundError) as exc:
        console.print(f"[bold red]✗ Erreur catalogue:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    inserted = 0
    updated = 0
    with console.status("[bold cyan]Synchronisation du catalogue…[/bold cyan]"):
        for agent in agents:
            existing = storage.get_agent_by_slug(agent.slug)
            if existing:
                # Update: keep existing ID, update data
                agent_to_save = agent.model_copy(update={"id": existing.id})
                storage.save_agent(agent_to_save)
                updated += 1
            else:
                storage.save_agent(agent)
                inserted += 1

    lines = []
    if inserted:
        lines.append(f"[bold green]+{inserted}[/bold green] agent(s) insérés")
    if updated:
        lines.append(f"[bold yellow]~{updated}[/bold yellow] agent(s) mis à jour")
    if not lines:
        lines.append("[dim]Aucun changement (déjà à jour)[/dim]")

    console.print(
        Panel(
            "  ".join(lines),
            title="✅  Synchronisation terminée",
            expand=False,
            border_style="green",
        )
    )

    # ── Tableau si --show ─────────────────────────────────────────────────────
    if show:
        all_agents = storage.list_agents()
        table = Table(
            title="🤖  Agents persistés dans ai_agents",
            show_lines=False,
            header_style="bold",
        )
        table.add_column("Slug", style="bold cyan", no_wrap=True)
        table.add_column("Nom")
        table.add_column("Rôle", justify="center")
        table.add_column("Provider", style="dim")
        table.add_column("Modèle", style="dim")
        table.add_column("Actif", justify="center")
        table.add_column("Mis à jour", style="dim", no_wrap=True)

        for a in all_agents:
            try:
                upd = a.updated_at.strftime("%d/%m %H:%M")
            except (ValueError, AttributeError):
                upd = str(a.updated_at)[:16]
            table.add_row(
                a.slug,
                a.name,
                _role_style(a.role.value),
                a.provider_id,
                a.model or "[dim]default[/dim]",
                "✅" if a.is_active else "❌",
                upd,
            )

        console.print(table)
        console.print(f"\n[dim]{len(all_agents)} agent(s) en base.[/dim]")
