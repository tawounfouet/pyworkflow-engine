"""
adapters/ai/tools/executor — Exécution de ToolCalls + boucle tool-calling LLM.

Usage::

    registry = ToolRegistry()
    registry.register("calculator", calc_tool.run)

    executor = ToolExecutor(registry)

    # Exécution unitaire
    result = executor.execute_call(tool_call)

    # Boucle complète tool-calling avec un client LLM
    final_response = executor.run_tool_loop(client, messages, max_iterations=10)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pyworkflow_engine.adapters.ai.tools.registry import ToolRegistry
from pyworkflow_engine.exceptions import AIToolNotFoundError
from pyworkflow_engine.models.ai.message import ToolCall, ToolResult
from pyworkflow_engine.ports.ai.llm import BaseLLMClient, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Exécuteur de ToolCalls avec support de la boucle tool-calling LLM."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    # ── Exécution unitaire ─────────────────────────────────────────────

    def execute_call(self, tool_call: ToolCall) -> ToolResult:
        """Exécute un appel de tool unique (sync)."""
        try:
            func = self.registry.get(tool_call.name)
        except AIToolNotFoundError:
            return ToolResult(
                tool_call_id=tool_call.id,
                output=f"Error: Tool '{tool_call.name}' not found in registry.",
                is_error=True,
            )
        try:
            result = func(**tool_call.arguments)
            output = (
                result
                if isinstance(result, str)
                else json.dumps(result, default=str, ensure_ascii=False)
            )
            return ToolResult(tool_call_id=tool_call.id, output=output, is_error=False)
        except Exception as exc:
            logger.warning("Tool '%s' execution failed: %s", tool_call.name, exc)
            return ToolResult(
                tool_call_id=tool_call.id,
                output=f"Error executing tool '{tool_call.name}': {exc}",
                is_error=True,
            )

    async def aexecute_call(self, tool_call: ToolCall) -> ToolResult:
        """Exécute un appel de tool unique (async)."""
        try:
            func = self.registry.get(tool_call.name)
        except AIToolNotFoundError:
            return ToolResult(
                tool_call_id=tool_call.id,
                output=f"Error: Tool '{tool_call.name}' not found in registry.",
                is_error=True,
            )
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(**tool_call.arguments)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: func(**tool_call.arguments)
                )
            output = (
                result
                if isinstance(result, str)
                else json.dumps(result, default=str, ensure_ascii=False)
            )
            return ToolResult(tool_call_id=tool_call.id, output=output, is_error=False)
        except Exception as exc:
            logger.warning("Tool '%s' async execution failed: %s", tool_call.name, exc)
            return ToolResult(
                tool_call_id=tool_call.id,
                output=f"Error executing tool '{tool_call.name}': {exc}",
                is_error=True,
            )

    # ── Boucle tool-calling ────────────────────────────────────────────

    def run_tool_loop(
        self,
        client: BaseLLMClient,
        messages: list[Any],
        *,
        max_iterations: int = 10,
        conversation_id: str = "",
    ) -> LLMResponse:
        """Boucle tool-calling synchrone : appelle le LLM, exécute les tools, recommence.

        Continue tant que le LLM demande des tool_calls, jusqu'à ``max_iterations``.

        Args:
            client: Client LLM à utiliser.
            messages: Messages de contexte (system + historique + user).
            max_iterations: Nombre max de boucles tool-calling.
            conversation_id: ID de la conversation (pour les messages créés).

        Returns:
            Dernière réponse LLM sans tool_calls.
        """
        from pyworkflow_engine.models.ai.message import Message  # noqa: PLC0415
        from pyworkflow_engine.models.ai.types import MessageRole  # noqa: PLC0415

        tool_schemas = [
            self.registry.get_definition(key).get_function_schema()
            for key in self.registry.keys()
            if self.registry.get_definition(key)
        ]

        current_messages = list(messages)
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            request = LLMRequest(
                messages=current_messages,
                tools=tool_schemas if tool_schemas else None,
            )
            response = client.complete(request)

            if not response.tool_calls:
                return response

            # Ajouter le message assistant avec les tool_calls
            assistant_msg = Message(
                content=response.content,
                role=MessageRole.ASSISTANT,
                conversation_id=conversation_id,
                metadata={
                    "tool_calls": [tc.model_dump() for tc in response.tool_calls]
                },
            )
            current_messages.append(assistant_msg)

            # Exécuter chaque tool_call et ajouter les résultats
            for tc_req in response.tool_calls:
                # Adapter ToolCallRequest → ToolCall (modèle message)
                tool_call = ToolCall(
                    id=tc_req.id,
                    name=tc_req.function_name,
                    arguments=tc_req.arguments,
                )
                tool_result = self.execute_call(tool_call)
                result_msg = Message(
                    content=tool_result.output,
                    role=MessageRole.TOOL,
                    conversation_id=conversation_id,
                    metadata={"tool_call_id": tool_result.tool_call_id},
                )
                current_messages.append(result_msg)

        logger.warning("Tool-calling loop reached max_iterations=%d", max_iterations)
        return client.complete(LLMRequest(messages=current_messages))
