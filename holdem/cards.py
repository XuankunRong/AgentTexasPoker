from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

RANKS = "23456789TJQKA"
SUITS = "shdc"
RANK_TO_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}
VALUE_TO_RANK = {v: k for k, v in RANK_TO_VALUE.items()}


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def value(self) -> int:
        return RANK_TO_VALUE[self.rank]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    @classmethod
    def from_str(cls, raw: str) -> "Card":
        if len(raw) != 2 or raw[0] not in RANKS or raw[1] not in SUITS:
            raise ValueError(f"Invalid card: {raw}")
        return cls(rank=raw[0], suit=raw[1])


class Deck:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.cards = [Card(r, s) for r in RANKS for s in SUITS]

    def shuffle(self) -> None:
        self._rng.shuffle(self.cards)

    def deal(self, n: int = 1) -> list[Card]:
        if n > len(self.cards):
            raise ValueError("Deck is empty")
        dealt, self.cards = self.cards[:n], self.cards[n:]
        return dealt


def _straight_high(values: Sequence[int]) -> int | None:
    uniq = sorted(set(values), reverse=True)
    if 14 in uniq:
        uniq.append(1)
    run = 1
    best = None
    for i in range(len(uniq) - 1):
        if uniq[i] - 1 == uniq[i + 1]:
            run += 1
            if run >= 5:
                best = uniq[i - 3]
        else:
            run = 1
    return best


def evaluate_5(cards: Sequence[Card]) -> tuple[int, tuple[int, ...]]:
    if len(cards) != 5:
        raise ValueError("evaluate_5 expects exactly 5 cards")
    values = sorted((c.value for c in cards), reverse=True)
    suits = [c.suit for c in cards]
    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1

    by_count_then_value = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    is_flush = len(set(suits)) == 1
    straight_high = _straight_high(values)
    is_straight = straight_high is not None

    if is_flush and is_straight:
        return (8, (straight_high,))
    if by_count_then_value[0][1] == 4:
        four = by_count_then_value[0][0]
        kicker = max(v for v in values if v != four)
        return (7, (four, kicker))
    if by_count_then_value[0][1] == 3 and by_count_then_value[1][1] == 2:
        return (6, (by_count_then_value[0][0], by_count_then_value[1][0]))
    if is_flush:
        return (5, tuple(sorted(values, reverse=True)))
    if is_straight:
        return (4, (straight_high,))
    if by_count_then_value[0][1] == 3:
        trips = by_count_then_value[0][0]
        kickers = sorted((v for v in values if v != trips), reverse=True)
        return (3, (trips, *kickers))
    if by_count_then_value[0][1] == 2 and by_count_then_value[1][1] == 2:
        pair_high = max(by_count_then_value[0][0], by_count_then_value[1][0])
        pair_low = min(by_count_then_value[0][0], by_count_then_value[1][0])
        kicker = max(v for v in values if v != pair_high and v != pair_low)
        return (2, (pair_high, pair_low, kicker))
    if by_count_then_value[0][1] == 2:
        pair = by_count_then_value[0][0]
        kickers = sorted((v for v in values if v != pair), reverse=True)
        return (1, (pair, *kickers))
    return (0, tuple(sorted(values, reverse=True)))


def evaluate_best(cards: Iterable[Card]) -> tuple[int, tuple[int, ...]]:
    all_cards = list(cards)
    if len(all_cards) < 5:
        raise ValueError("Need at least 5 cards for evaluation")
    return max(evaluate_5(combo) for combo in combinations(all_cards, 5))
