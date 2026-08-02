"""Base exporter interface for output destinations."""

from abc import ABC, abstractmethod
from typing import Any


class BaseExporter(ABC):
    """Abstract base class for output exporters."""

    @abstractmethod
    def export_registrations(self, registrations: list[Any]) -> int:
        """Export a list of registration models or dicts. Returns count exported."""

    @abstractmethod
    def export_communications(self, communications: list[Any]) -> int:
        """Export a list of communication report models or dicts. Returns count exported."""

    @abstractmethod
    def close(self) -> None:
        """Clean up resources if needed."""
