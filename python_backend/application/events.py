from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class ApplicationEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus(Protocol):
    def publish(self, event: ApplicationEvent) -> None:
        ...


class InMemoryEventBus:
    def __init__(self) -> None:
        self.events: list[ApplicationEvent] = []
        self._handlers: dict[str, list[Callable[[ApplicationEvent], None]]] = {}

    def subscribe(self, event_name: str, handler: Callable[[ApplicationEvent], None]) -> None:
        self._handlers.setdefault(event_name, []).append(handler)

    def publish(self, event: ApplicationEvent) -> None:
        self.events.append(event)
        for handler in self._handlers.get(event.name, []):
            handler(event)
