from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from holdem.cards import Card


@dataclass
class Action:
    action: str
    amount: int = 0


@dataclass
class AgentView:
    hand_id: int
    street: str
    player_name: str
    player_position: str
    player_stack: int
    player_bet: int
    to_call: int
    min_raise_to: int
    pot: int
    community_cards: Sequence[Card]
    hole_cards: Sequence[Card]
    active_players: Sequence[str]
    legal_actions: Sequence[str]
    table_positions: dict[str, str] = field(default_factory=dict)
    players_state: Sequence[dict[str, object]] = field(default_factory=list)
    effective_stack: int = 0


@dataclass
class HandResult:
    hand_id: int
    winners: list[str]
    pot: int
    showdown: bool
