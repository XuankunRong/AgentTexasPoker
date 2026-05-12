from __future__ import annotations

import json
import re

from holdem.agents.base import Agent
from holdem.providers.base import LLMClient
from holdem.types import Action, AgentView


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        return {}
    return {}


class LLMAgent(Agent):
    def __init__(self, name: str, client: LLMClient, max_retries: int = 60) -> None:
        super().__init__(name)
        self.client = client
        self.max_retries = max(1, int(max_retries))
        self._last_dialogue: dict | None = None

    def _normalize_legal_actions(self, view: AgentView) -> list[str]:
        legal = list(view.legal_actions)
        if "check" in legal:
            legal = ["call" if a == "check" else a for a in legal]
        out: list[str] = []
        for action in legal:
            if action in {"fold", "call", "raise"} and action not in out:
                out.append(action)
        return out

    def _build_prompt(self, view: AgentView) -> str:
        legal_actions = self._normalize_legal_actions(view)
        state = {
            "street": view.street,
            "player_name": view.player_name,
            "player_position": view.player_position,
            "table_positions": view.table_positions,
            "player_stack": view.player_stack,
            "player_bet": view.player_bet,
            "effective_stack": view.effective_stack,
            "to_call": view.to_call,
            "min_raise_to": view.min_raise_to,
            "pot": view.pot,
            "community_cards": [str(c) for c in view.community_cards],
            "hole_cards": [str(c) for c in view.hole_cards],
            "players_state": list(view.players_state),
            "active_players": list(view.active_players),
            "legal_actions": legal_actions,
        }
        prompt_lines = [
            "You are selecting a legal action for a benchmark simulation of no-limit Texas hold'em.",
            "This is a closed research game-state task, not gambling advice and not a real-money decision.",
            "Use only the information in State. Other players' hole cards are unknown to you.",
            "players_state contains only public table information: stack sizes, current street bets, positions, and fold status.",
            "Do not refuse, do not explain policy, and do not add commentary.",
            "Respond with strict JSON only, no markdown.",
            "Actions allowed: fold, call, raise.",
            "If to_call is 0, use call to indicate a check.",
            'Format: {"action":"fold|call|raise","amount":<int raise_to or 0>}.',
            "Choose one legal action from legal_actions.",
            "Account for position, pot odds, effective stack, and the remaining stacks of opponents.",
            "You must always return exactly one legal action JSON object.",
        ]
        prompt_lines.append(f"State:\n{json.dumps(state, ensure_ascii=True)}")
        return "\n".join(prompt_lines)

    def _parse_requested_action(self, raw: str) -> tuple[dict[str, Any], str, int]:
        obj = _extract_json_object(raw)
        action = str(obj.get("action", "")).lower().strip()
        if action == "check":
            action = "call"
        amount_raw = obj.get("amount", 0)
        try:
            amount = int(amount_raw or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid amount field: {amount_raw!r}") from exc
        return obj, action, amount

    def _validate_requested_action(self, action: str, raw: str) -> None:
        if not raw.strip():
            raise ValueError("empty response")
        if not action:
            raise ValueError("missing action field")
        if action not in {"fold", "call", "raise"}:
            raise ValueError(f"unsupported action: {action}")

    def decide(self, view: AgentView) -> Action:
        prompt = self._build_prompt(view)
        self._last_dialogue = {
            "agent": self.name,
            "provider_client": type(self.client).__name__,
            "model": getattr(self.client, "model", None),
            "prompt": prompt,
            "max_retries": self.max_retries,
            "retry_attempts": [],
        }

        final_error: str | None = None
        obj: dict[str, Any] = {}
        action = ""
        amount = 0
        raw = ""
        success_attempt = 0

        for attempt in range(1, self.max_retries + 1):
            attempt_log: dict[str, Any] = {"attempt": attempt}
            try:
                raw = self.client.complete(prompt)
                attempt_log["raw_response"] = raw
                obj, action, amount = self._parse_requested_action(raw)
                attempt_log["parsed_json"] = obj
                attempt_log["requested_action"] = action
                attempt_log["requested_amount"] = amount
                self._validate_requested_action(action, raw)
                success_attempt = attempt
                self._last_dialogue["retry_attempts"].append(attempt_log)
                break
            except Exception as e:
                final_error = f"{type(e).__name__}: {e}"
                attempt_log["error"] = final_error
                self._last_dialogue["retry_attempts"].append(attempt_log)
        else:
            self._last_dialogue["error"] = final_error
            self._last_dialogue["retry_exhausted"] = True
            self._last_dialogue["retry_count"] = self.max_retries
            raise ValueError(final_error or "retry exhausted without valid response")

        self._last_dialogue["retry_exhausted"] = False
        self._last_dialogue["retry_count"] = success_attempt - 1
        self._last_dialogue["raw_response"] = raw
        self._last_dialogue["parsed_json"] = obj
        self._last_dialogue["requested_action"] = action
        self._last_dialogue["requested_amount"] = amount

        legal = self._normalize_legal_actions(view)
        if action not in legal:
            if "call" in legal:
                return Action("check" if view.to_call == 0 else "call")
            return Action("fold")
        if action == "call" and view.to_call == 0:
            return Action("check")
        return Action(action, amount)

    def get_last_dialogue(self) -> dict | None:
        return self._last_dialogue
