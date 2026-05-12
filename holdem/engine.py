from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Callable

from holdem.agents.base import Agent
from holdem.cards import Card, Deck, evaluate_best
from holdem.types import Action, AgentView, HandResult


@dataclass
class Seat:
    name: str
    agent: Agent
    initial_stack: int
    stack: int
    hole_cards: list[Card]
    folded: bool
    street_bet: int
    hand_bet: int

    def reset_for_new_hand(self) -> None:
        self.hole_cards = []
        self.folded = False
        self.street_bet = 0
        self.hand_bet = 0


class HoldemEngine:
    def __init__(
        self,
        seats: list[tuple[str, Agent]],
        starting_stack: int = 1000,
        starting_stacks: dict[str, int] | None = None,
        small_blind: int = 5,
        big_blind: int = 10,
        max_raises_per_street: int = 3,
        seed: int | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        reset_stacks_each_hand: bool = False,
    ) -> None:
        if len(seats) < 2:
            raise ValueError("Need at least 2 players")
        self.seats = [
            Seat(
                name=name,
                agent=agent,
                initial_stack=int((starting_stacks or {}).get(name, starting_stack)),
                stack=int((starting_stacks or {}).get(name, starting_stack)),
                hole_cards=[],
                folded=False,
                street_bet=0,
                hand_bet=0,
            )
            for name, agent in seats
        ]
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.starting_stack = starting_stack
        self.max_raises_per_street = max_raises_per_street
        self.seed = seed
        self.reset_stacks_each_hand = reset_stacks_each_hand

        self.dealer_idx = -1
        self.hand_id = 0
        self.pot = 0
        self.community_cards: list[Card] = []
        self.hands_won: dict[str, int] = {name: 0 for name, _ in seats}
        self._deck: Deck | None = None
        self._current_participants: set[int] = set()
        self.last_hand_trace: dict | None = None
        self.event_sink = event_sink
        self._event_seq = 0

    def play(self, hands: int = 100) -> list[HandResult]:
        results: list[HandResult] = []
        for _ in range(hands):
            if self.reset_stacks_each_hand:
                for seat in self.seats:
                    seat.stack = seat.initial_stack
            if len(self._live_for_hand()) < 2:
                break
            results.append(self.play_hand())
        return results

    def set_blinds(self, small_blind: int, big_blind: int) -> None:
        if small_blind <= 0 or big_blind <= 0:
            raise ValueError("Blinds must be > 0")
        if small_blind >= big_blind:
            raise ValueError("small_blind must be < big_blind")
        self.small_blind = small_blind
        self.big_blind = big_blind

    def live_player_names(self) -> list[str]:
        return [self.seats[i].name for i in self._live_for_hand()]

    def _emit_event(self, payload: dict[str, Any]) -> None:
        if self.event_sink is None:
            return
        self._event_seq += 1
        event = {
            "seq": self._event_seq,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        try:
            self.event_sink(event)
        except Exception:
            # Logging failures should never break game progression.
            pass

    def _order_from(self, start: int, participants: list[int]) -> list[int]:
        pset = set(participants)
        n = len(self.seats)
        out: list[int] = []
        for offset in range(n):
            idx = (start + offset) % n
            if idx in pset:
                out.append(idx)
        return out

    def _position_labels(self, live: list[int]) -> dict[int, str]:
        order = self._order_from(self.dealer_idx, live)
        n = len(order)
        if n == 2:
            labels = ["BTN/SB", "BB"]
        elif n == 3:
            labels = ["BTN", "SB", "BB"]
        elif n == 4:
            labels = ["BTN", "SB", "BB", "UTG"]
        elif n == 5:
            labels = ["BTN", "SB", "BB", "UTG", "CO"]
        elif n == 6:
            labels = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
        else:
            labels = ["BTN", "SB", "BB"] + [f"MP{i + 1}" for i in range(max(0, n - 3))]
        return {idx: labels[i] for i, idx in enumerate(order)}

    def play_hand(self) -> HandResult:
        live = self._live_for_hand()
        if len(live) < 2:
            raise RuntimeError("Not enough players to continue")

        self.hand_id += 1
        self.pot = 0
        self.community_cards = []
        self._current_participants = set(live)
        stacks_before_hand = {self.seats[i].name: self.seats[i].stack for i in live}
        for s in self.seats:
            s.reset_for_new_hand()
        for i, s in enumerate(self.seats):
            s.folded = i not in self._current_participants

        self.dealer_idx = self._next_live_index(self.dealer_idx + 1)
        self._deck = Deck(seed=(None if self.seed is None else self.seed + self.hand_id))
        self._deck.shuffle()
        self._deal_hole_cards(live)

        if len(live) == 2:
            sb_idx = self.dealer_idx
            bb_idx = self._next_live_index(self.dealer_idx + 1)
        else:
            sb_idx = self._next_live_index(self.dealer_idx + 1)
            bb_idx = self._next_live_index(sb_idx + 1)

        if len(live) == 2:
            first_preflop = sb_idx
        else:
            first_preflop = self._next_live_index(bb_idx + 1)
        position_by_index = self._position_labels(live)
        positions_by_player = {
            self.seats[i].name: position_by_index.get(i, "") for i in live
        }
        table_order = [self.seats[i].name for i in self._order_from(self.dealer_idx, live)]
        preflop_order = [self.seats[i].name for i in self._order_from(first_preflop, live)]
        self._emit_event(
            {
                "type": "hand_start",
                "hand_id": self.hand_id,
                "participants": [self.seats[i].name for i in live],
                "table_order_from_dealer": table_order,
                "preflop_action_order": preflop_order,
                "dealer": self.seats[self.dealer_idx].name,
                "small_blind": {"player": self.seats[sb_idx].name, "amount": self.small_blind},
                "big_blind": {"player": self.seats[bb_idx].name, "amount": self.big_blind},
                "positions_by_player": positions_by_player,
                "hole_cards": {
                    self.seats[i].name: [str(c) for c in self.seats[i].hole_cards]
                    for i in live
                },
                "stacks_before_hand": stacks_before_hand,
                "pot_before_blinds": self.pot,
            }
        )
        sb_posted = self._commit_blind(sb_idx, self.small_blind)
        self._emit_event(
            {
                "type": "blind_post",
                "hand_id": self.hand_id,
                "blind": "small_blind",
                "player": self.seats[sb_idx].name,
                "player_position": position_by_index.get(sb_idx, ""),
                "amount": sb_posted,
                "pot_after": self.pot,
            }
        )
        bb_posted = self._commit_blind(bb_idx, self.big_blind)
        self._emit_event(
            {
                "type": "blind_post",
                "hand_id": self.hand_id,
                "blind": "big_blind",
                "player": self.seats[bb_idx].name,
                "player_position": position_by_index.get(bb_idx, ""),
                "amount": bb_posted,
                "pot_after": self.pot,
            }
        )
        self._init_hand_trace(
            live=live,
            sb_idx=sb_idx,
            bb_idx=bb_idx,
            positions_by_player=positions_by_player,
        )

        current_bet, last_raise = self._betting_round(
            participants=live,
            position_by_index=position_by_index,
            street="preflop",
            first_to_act=first_preflop,
            current_bet=max(self.seats[sb_idx].street_bet, self.seats[bb_idx].street_bet),
            last_raise=self.big_blind,
        )
        if self._count_unfolded(live) == 1:
            result = self._award_without_showdown()
            self._finalize_hand_trace(result)
            return result

        for street, board_cards in [("flop", 3), ("turn", 1), ("river", 1)]:
            for i in live:
                self.seats[i].street_bet = 0
            self.community_cards.extend(self._deck.deal(board_cards))

            if self._count_actionable(live) <= 1:
                continue

            first_postflop = self._next_active_in_hand_index(self.dealer_idx + 1, live)
            current_bet, last_raise = self._betting_round(
                participants=live,
                position_by_index=position_by_index,
                street=street,
                first_to_act=first_postflop,
                current_bet=0,
                last_raise=self.big_blind,
            )
            if self._count_unfolded(live) == 1:
                result = self._award_without_showdown()
                self._finalize_hand_trace(result)
                return result

        result = self._showdown()
        self._finalize_hand_trace(result)
        return result

    def stacks(self) -> dict[str, int]:
        return {s.name: s.stack for s in self.seats}

    def _live_for_hand(self) -> list[int]:
        return [i for i, s in enumerate(self.seats) if s.stack > 0]

    def _count_unfolded(self, indices: list[int]) -> int:
        return sum(1 for i in indices if not self.seats[i].folded)

    def _count_actionable(self, indices: list[int]) -> int:
        return sum(1 for i in indices if not self.seats[i].folded and self.seats[i].stack > 0)

    def _next_live_index(self, start: int) -> int:
        n = len(self.seats)
        for offset in range(n):
            idx = (start + offset) % n
            if self.seats[idx].stack > 0:
                return idx
        raise RuntimeError("No live player found")

    def _next_active_in_hand_index(self, start: int, participants: list[int]) -> int:
        idx = self._next_index(
            start,
            lambda i: i in participants and not self.seats[i].folded and self.seats[i].stack > 0,
        )
        if idx is None:
            raise RuntimeError("No active in-hand player found")
        return idx

    def _next_index(self, start: int, pred: Callable[[int], bool]) -> int | None:
        n = len(self.seats)
        for offset in range(n):
            idx = (start + offset) % n
            if pred(idx):
                return idx
        return None

    def _deal_hole_cards(self, live: list[int]) -> None:
        for _ in range(2):
            for i in live:
                self.seats[i].hole_cards.extend(self._deck.deal(1))

    def _init_hand_trace(
        self,
        live: list[int],
        sb_idx: int,
        bb_idx: int,
        positions_by_player: dict[str, str],
    ) -> None:
        self.last_hand_trace = {
            "hand_id": self.hand_id,
            "dealer": self.seats[self.dealer_idx].name,
            "small_blind": {"name": self.seats[sb_idx].name, "amount": self.small_blind},
            "big_blind": {"name": self.seats[bb_idx].name, "amount": self.big_blind},
            "positions_by_player": positions_by_player,
            "hole_cards": {
                self.seats[i].name: [str(c) for c in self.seats[i].hole_cards]
                for i in live
            },
            "streets": [],
        }

    def _finalize_hand_trace(self, result: HandResult) -> None:
        if self.last_hand_trace is None:
            return
        self.last_hand_trace["result"] = {
            "winners": list(result.winners),
            "pot": result.pot,
            "showdown": result.showdown,
        }
        self.last_hand_trace["stacks"] = self.stacks()
        self._emit_event(
            {
                "type": "hand_end",
                "hand_id": self.hand_id,
                "result": {
                    "winners": list(result.winners),
                    "pot": result.pot,
                    "showdown": result.showdown,
                },
                "stacks": self.stacks(),
                "community_cards": [str(c) for c in self.community_cards],
            }
        )

    def _commit(self, idx: int, amount: int) -> int:
        seat = self.seats[idx]
        if amount < 0:
            raise ValueError("amount must be >= 0")
        actual = min(amount, seat.stack)
        seat.stack -= actual
        seat.street_bet += actual
        seat.hand_bet += actual
        self.pot += actual
        return actual

    def _commit_blind(self, idx: int, blind: int) -> int:
        return self._commit(idx, blind)

    def _legal_actions(
        self,
        idx: int,
        current_bet: int,
        last_raise: int,
        raises: int,
    ) -> tuple[list[str], int, int]:
        seat = self.seats[idx]
        to_call = max(0, current_bet - seat.street_bet)
        min_raise_to = (current_bet + last_raise) if current_bet > 0 else self.big_blind

        legal: list[str] = []
        if to_call > 0:
            legal.append("fold")
            if seat.stack > 0:
                legal.append("call")
        else:
            legal.append("check")

        if raises < self.max_raises_per_street:
            required = min_raise_to - seat.street_bet
            if required > 0 and seat.stack >= required:
                legal.append("raise")
        return legal, to_call, min_raise_to

    def _sanitize_action(self, action: Action, legal: list[str], to_call: int) -> Action:
        if action.action in legal:
            return action
        if to_call == 0 and "check" in legal:
            return Action("check")
        if to_call > 0 and "call" in legal:
            return Action("call")
        return Action("fold")

    def _betting_round(
        self,
        participants: list[int],
        position_by_index: dict[int, str],
        street: str,
        first_to_act: int,
        current_bet: int,
        last_raise: int,
    ) -> tuple[int, int]:
        raises = 0
        street_trace: dict | None = None
        if self.last_hand_trace is not None:
            street_trace = {
                "street": street,
                "board": [str(c) for c in self.community_cards],
                "actions": [],
            }
            self.last_hand_trace["streets"].append(street_trace)
        self._emit_event(
            {
                "type": "street_start",
                "hand_id": self.hand_id,
                "street": street,
                "board": [str(c) for c in self.community_cards],
                "pot": self.pot,
                "active_players": [
                    self.seats[i].name for i in participants if not self.seats[i].folded
                ],
            }
        )
        to_act = {
            i
            for i in participants
            if not self.seats[i].folded and self.seats[i].stack > 0
        }
        pointer = first_to_act

        while len([i for i in participants if not self.seats[i].folded]) > 1 and to_act:
            idx = self._next_index(
                pointer,
                lambda i: i in to_act and not self.seats[i].folded and self.seats[i].stack > 0,
            )
            if idx is None:
                break
            seat = self.seats[idx]
            legal, to_call, min_raise_to = self._legal_actions(idx, current_bet, last_raise, raises)
            active_names = [self.seats[i].name for i in participants if not self.seats[i].folded]
            public_players_state = [
                {
                    "name": self.seats[i].name,
                    "position": position_by_index.get(i, ""),
                    "stack": self.seats[i].stack,
                    "bet": self.seats[i].street_bet,
                    "folded": self.seats[i].folded,
                    "active_in_hand": not self.seats[i].folded,
                }
                for i in participants
            ]
            active_opponent_stacks = [
                self.seats[i].stack
                for i in participants
                if i != idx and not self.seats[i].folded and self.seats[i].stack > 0
            ]
            effective_stack = seat.stack
            if active_opponent_stacks:
                effective_stack = min(seat.stack, max(0, min(active_opponent_stacks)))
            view = AgentView(
                hand_id=self.hand_id,
                street=street,
                player_name=seat.name,
                player_position=position_by_index.get(idx, ""),
                player_stack=seat.stack,
                player_bet=seat.street_bet,
                to_call=to_call,
                min_raise_to=min_raise_to,
                pot=self.pot,
                community_cards=list(self.community_cards),
                hole_cards=list(seat.hole_cards),
                active_players=active_names,
                legal_actions=legal,
                table_positions={
                    self.seats[i].name: position_by_index.get(i, "") for i in participants
                },
                players_state=public_players_state,
                effective_stack=effective_stack,
            )
            try:
                action = seat.agent.decide(view)
                decide_error = None
            except Exception as e:
                action = Action("fold" if to_call > 0 else "check")
                decide_error = f"{type(e).__name__}: {e}"
            requested_action = action.action
            requested_amount = action.amount
            action = self._sanitize_action(action, legal, to_call)
            pot_before = self.pot
            stack_before = seat.stack
            bet_before = seat.street_bet
            final_action = action.action
            final_amount = 0
            dialogue = seat.agent.get_last_dialogue()

            if action.action == "fold":
                seat.folded = True
                to_act.discard(idx)
            elif action.action == "check":
                to_act.discard(idx)
            elif action.action == "call":
                final_amount = self._commit(idx, to_call)
                to_act.discard(idx)
            elif action.action == "raise":
                min_to = min_raise_to
                target = max(action.amount, min_to)
                if target <= current_bet:
                    target = min_to
                required = target - seat.street_bet
                if required > seat.stack:
                    if to_call == 0:
                        final_action = "check"
                        to_act.discard(idx)
                    else:
                        if seat.stack > 0:
                            final_amount = self._commit(idx, to_call)
                            final_action = "call"
                            to_act.discard(idx)
                        else:
                            final_action = "fold"
                            seat.folded = True
                            to_act.discard(idx)
                else:
                    prev_bet = current_bet
                    self._commit(idx, required)
                    current_bet = target
                    last_raise = current_bet - prev_bet if prev_bet > 0 else current_bet
                    raises += 1
                    final_amount = target
                    to_act = {
                        i
                        for i in participants
                        if i != idx and not self.seats[i].folded and self.seats[i].stack > 0
                    }

            if street_trace is not None:
                street_trace["actions"].append(
                    {
                        "player": seat.name,
                        "action": final_action,
                        "amount": final_amount,
                        "position": position_by_index.get(idx, ""),
                        "to_call": to_call,
                        "min_raise_to": min_raise_to,
                        "legal_actions": list(legal),
                        "pot_before": pot_before,
                        "pot_after": self.pot,
                        "stack_before": stack_before,
                        "stack_after": seat.stack,
                        "bet_before": bet_before,
                        "bet_after": seat.street_bet,
                        "agent_dialogue": dialogue,
                        "decide_error": decide_error,
                    }
                )
            self._emit_event(
                {
                    "type": "action",
                    "hand_id": self.hand_id,
                    "street": street,
                    "player": seat.name,
                    "player_position": position_by_index.get(idx, ""),
                    "requested_action": requested_action,
                    "requested_amount": requested_amount,
                    "final_action": final_action,
                    "final_amount": final_amount,
                    "to_call": to_call,
                    "min_raise_to": min_raise_to,
                    "legal_actions": list(legal),
                    "pot_before": pot_before,
                    "pot_after": self.pot,
                    "stack_before": stack_before,
                    "stack_after": seat.stack,
                    "bet_before": bet_before,
                    "bet_after": seat.street_bet,
                    "active_players_after": [
                        self.seats[i].name for i in participants if not self.seats[i].folded
                    ],
                    "agent_dialogue": dialogue,
                    "decide_error": decide_error,
                }
            )

            pointer = (idx + 1) % len(self.seats)

        return current_bet, last_raise

    def _award_without_showdown(self) -> HandResult:
        winners = [self.seats[i] for i in self._current_participants if not self.seats[i].folded]
        if not winners:
            raise RuntimeError("No winner found when awarding without showdown")
        winner = winners[0]
        winner.stack += self.pot
        self.hands_won[winner.name] += 1
        return HandResult(hand_id=self.hand_id, winners=[winner.name], pot=self.pot, showdown=False)

    def _showdown(self) -> HandResult:
        alive = [self.seats[i] for i in self._current_participants if not self.seats[i].folded]
        ranks = {s.name: evaluate_best(list(s.hole_cards) + list(self.community_cards)) for s in alive}

        contributions = {
            i: self.seats[i].hand_bet for i in self._current_participants if self.seats[i].hand_bet > 0
        }
        if not contributions:
            raise RuntimeError("No pot contributions found at showdown")

        levels = sorted(set(contributions.values()))
        remaining = {i for i, amount in contributions.items() if amount > 0}
        prev_level = 0
        winners_seen: dict[str, None] = {}

        for level in levels:
            tranche = level - prev_level
            pot_slice = tranche * len(remaining)
            eligible = [self.seats[i] for i in remaining if not self.seats[i].folded]
            if eligible and pot_slice > 0:
                eligible_ranks = {s.name: ranks[s.name] for s in eligible}
                best = max(eligible_ranks.values())
                winners = [s for s in eligible if eligible_ranks[s.name] == best]
                base = pot_slice // len(winners)
                remainder = pot_slice % len(winners)
                for s in winners:
                    s.stack += base
                    winners_seen[s.name] = None
                for i in range(remainder):
                    winners[i % len(winners)].stack += 1
            prev_level = level
            remaining = {i for i in remaining if contributions[i] > level}

        for name in winners_seen:
            self.hands_won[name] += 1
        return HandResult(
            hand_id=self.hand_id,
            winners=list(winners_seen.keys()),
            pot=self.pot,
            showdown=True,
        )
