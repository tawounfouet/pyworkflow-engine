"""RegistryPort — contrat d'accès au registre des connecteurs."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Type


class RegistryPort(ABC):
    """Port for connector class registry."""

    @abstractmethod
    def register(self, name: str, connector_cls: Type[Any]) -> None: ...

    @abstractmethod
    def get(self, name: str) -> Type[Any]: ...

    @abstractmethod
    def is_registered(self, name: str) -> bool: ...

    @abstractmethod
    def list_names(self) -> List[str]: ...

    @abstractmethod
    def clear(self) -> None: ...
