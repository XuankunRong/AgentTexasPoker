from __future__ import annotations

from abc import ABC, abstractmethod

from holdem.types import Action, AgentView


class Agent(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def decide(self, view: AgentView) -> Action:
        raise NotImplementedError

    def get_last_dialogue(self) -> dict | None:
        return None
