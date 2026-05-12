from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PlayerRiskMetrics:
    hands_played: int = 0
    hands_won: int = 0
    entered_hands: int = 0
    vpip_hands: int = 0
    pfr_hands: int = 0
    postflop_raises: int = 0
    postflop_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        win_rate = self.hands_won / self.entered_hands if self.entered_hands > 0 else None
        vpip = self.vpip_hands / self.hands_played if self.hands_played > 0 else 0.0
        pfr = self.pfr_hands / self.hands_played if self.hands_played > 0 else 0.0
        af = self.postflop_raises / self.postflop_calls if self.postflop_calls > 0 else float("inf")
        return {
            "hands_played": self.hands_played,
            "hands_won": self.hands_won,
            "entered_hands": self.entered_hands,
            "vpip_hands": self.vpip_hands,
            "pfr_hands": self.pfr_hands,
            "postflop_raises": self.postflop_raises,
            "postflop_calls": self.postflop_calls,
            "win_rate": None if win_rate is None else round(win_rate, 4),
            "vpip": round(vpip, 4),
            "pfr": round(pfr, 4),
            "aggression_factor": None if af == float("inf") else round(af, 4),
            "aggression_factor_raw": "inf" if af == float("inf") else round(af, 6),
        }


@dataclass
class PlayerRetryStats:
    decisions: int = 0
    decisions_with_retry: int = 0
    retry_attempts_total: int = 0
    retry_extra_total: int = 0
    failed_attempts_total: int = 0
    succeeded_after_retry: int = 0
    exhausted_after_retry: int = 0
    error_categories: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        top_issue_category = ""
        top_issue_count = 0
        issue_summary = ""
        if self.error_categories:
            top_issue_category, top_issue_count = max(
                self.error_categories.items(),
                key=lambda item: item[1],
            )
            ordered = sorted(self.error_categories.items(), key=lambda item: (-item[1], item[0]))
            issue_summary = ", ".join(
                f"{retry_issue_label(category)} {count}" for category, count in ordered[:3]
            )
        return {
            "decisions": self.decisions,
            "decisions_with_retry": self.decisions_with_retry,
            "retry_attempts_total": self.retry_attempts_total,
            "retry_extra_total": self.retry_extra_total,
            "failed_attempts_total": self.failed_attempts_total,
            "succeeded_after_retry": self.succeeded_after_retry,
            "exhausted_after_retry": self.exhausted_after_retry,
            "error_categories": dict(sorted(self.error_categories.items())),
            "top_issue_category": top_issue_category,
            "top_issue_label": retry_issue_label(top_issue_category) if top_issue_category else "",
            "top_issue_count": top_issue_count,
            "issue_summary": issue_summary,
        }


@dataclass
class _HandRiskState:
    participants: list[str]
    folded: set[str]
    entered_done: set[str]
    vpip_done: set[str]
    pfr_done: set[str]


def compute_risk_metrics(
    events: list[dict[str, Any]],
    *,
    seed: int = 7,
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, PlayerRiskMetrics] = {}
    hand_state: dict[int, _HandRiskState] = {}

    for event in events:
        event_type = str(event.get("type", ""))
        hand_id = int(event.get("hand_id", 0) or 0)

        if event_type == "hand_start":
            participants = [str(p) for p in (event.get("participants", []) or [])]
            hand_state[hand_id] = _HandRiskState(
                participants=participants,
                folded=set(),
                entered_done=set(),
                vpip_done=set(),
                pfr_done=set(),
            )
            for name in participants:
                metrics.setdefault(name, PlayerRiskMetrics()).hands_played += 1
            continue

        if hand_id <= 0:
            continue
        state = hand_state.get(hand_id)
        if state is None:
            continue

        if event_type != "action":
            if event_type == "hand_end":
                winners = [str(w) for w in ((event.get("result", {}) or {}).get("winners", []) or [])]
                for name in winners:
                    metrics.setdefault(name, PlayerRiskMetrics()).hands_won += 1
                hand_state.pop(hand_id, None)
            continue

        player = str(event.get("player", ""))
        if not player:
            continue
        pm = metrics.setdefault(player, PlayerRiskMetrics())
        street = str(event.get("street", ""))
        action = str(event.get("final_action", ""))

        if street == "preflop":
            if action in {"check", "call", "raise"} and player not in state.entered_done:
                pm.entered_hands += 1
                state.entered_done.add(player)
            if action in {"call", "raise"} and player not in state.vpip_done:
                pm.vpip_hands += 1
                state.vpip_done.add(player)
            if action == "raise" and player not in state.pfr_done:
                pm.pfr_hands += 1
                state.pfr_done.add(player)
        else:
            if action == "call":
                pm.postflop_calls += 1
            elif action == "raise":
                pm.postflop_raises += 1

        if action == "fold":
            state.folded.add(player)

    return {name: stat.to_dict() for name, stat in sorted(metrics.items())}


def load_events(events_path: str | Path) -> list[dict[str, Any]]:
    path = Path(events_path)
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    out.sort(key=lambda e: int(e.get("seq", 0) or 0))
    return out


def _classify_retry_error(error: str, raw_response: Any = None) -> str:
    err = str(error or "").strip()
    err_lower = err.lower()
    raw = str(raw_response or "").strip()
    raw_lower = raw.lower()

    if "http error 403" in err_lower or "httperror: 403" in err_lower or "forbidden" in err_lower:
        return "auth_forbidden"
    if "http error 401" in err_lower or "httperror: 401" in err_lower or "unauthorized" in err_lower:
        return "auth_unauthorized"
    if "http error 429" in err_lower or "rate limit" in err_lower:
        return "rate_limited"
    if "http error 500" in err_lower or "httperror: 500" in err_lower or "internal server error" in err_lower:
        return "server_500"
    if "operation timed out" in err_lower or "timed out" in err_lower or "timeout" in err_lower:
        return "timeout"
    if "unexpected_eof_while_reading" in err_lower or "ssl" in err_lower or "handshake" in err_lower:
        return "ssl_network"
    if "urlopen error" in err_lower or "temporary failure in name resolution" in err_lower:
        return "network_error"
    if "operation not permitted" in err_lower:
        return "network_permission"
    if "empty response" in err_lower:
        return "empty_response"
    if "invalid amount field" in err_lower:
        return "invalid_amount"
    if "unsupported action" in err_lower:
        return "unsupported_action"
    if "missing action field" in err_lower:
        if not raw:
            return "empty_response"
        if raw in {"{}", "[]", "null"}:
            return "empty_json"
        refusal_markers = [
            "i don't play poker",
            "i dont play poker",
            "i do not play poker",
            "don't play poker",
            "do not play poker",
            "gambling decisions",
            "can't discuss that",
            "cannot discuss that",
            "don't assist with gambling",
            "cannot assist with gambling",
            "don't provide gambling",
            "cannot provide gambling",
        ]
        if any(marker in raw_lower for marker in refusal_markers):
            return "refusal"
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "action" not in parsed:
                return "json_missing_action"
        except Exception:
            pass
        if "{" in raw and "}" in raw:
            return "malformed_or_mixed_json"
        return "non_json_text"
    return "other"


def retry_issue_label(category: str) -> str:
    labels = {
        "auth_forbidden": "403 forbidden",
        "auth_unauthorized": "401 unauthorized",
        "rate_limited": "rate limit",
        "server_500": "server 500",
        "timeout": "timeout",
        "ssl_network": "SSL/network",
        "network_error": "network error",
        "network_permission": "network blocked",
        "empty_response": "empty response",
        "empty_json": "empty JSON",
        "json_missing_action": "JSON missing action",
        "refusal": "model refusal",
        "malformed_or_mixed_json": "bad/mixed JSON",
        "non_json_text": "non-JSON text",
        "unsupported_action": "unsupported action",
        "invalid_amount": "invalid amount",
        "other": "other",
    }
    return labels.get(category, category)


def compute_retry_summary(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, PlayerRetryStats] = {}
    for event in events:
        if str(event.get("type", "")) != "action":
            continue
        player = str(event.get("player", "")).strip()
        if not player:
            continue
        row = stats.setdefault(player, PlayerRetryStats())
        row.decisions += 1

        dialogue = event.get("agent_dialogue")
        if not isinstance(dialogue, dict):
            continue
        retry_attempts = dialogue.get("retry_attempts")
        if not isinstance(retry_attempts, list) or not retry_attempts:
            continue

        attempts_used = len(retry_attempts)
        failed_attempts = sum(1 for attempt in retry_attempts if isinstance(attempt, dict) and attempt.get("error"))
        row.retry_attempts_total += attempts_used
        row.retry_extra_total += max(0, attempts_used - 1)
        row.failed_attempts_total += failed_attempts
        for attempt in retry_attempts:
            if not isinstance(attempt, dict):
                continue
            err = attempt.get("error")
            if not err:
                continue
            category = _classify_retry_error(str(err), attempt.get("raw_response"))
            row.error_categories[category] = row.error_categories.get(category, 0) + 1

        retry_count = dialogue.get("retry_count", 0)
        retry_exhausted = bool(dialogue.get("retry_exhausted", False))
        if int(retry_count or 0) > 0 or retry_exhausted:
            row.decisions_with_retry += 1
        if retry_exhausted:
            row.exhausted_after_retry += 1
        elif int(retry_count or 0) > 0:
            row.succeeded_after_retry += 1

    return {player: row.to_dict() for player, row in sorted(stats.items())}


def compute_risk_metrics_from_file(
    events_path: str | Path,
    *,
    seed: int = 7,
) -> dict[str, dict[str, Any]]:
    events = load_events(events_path)
    return compute_risk_metrics(
        events,
        seed=seed,
    )


def compute_retry_summary_from_file(events_path: str | Path) -> dict[str, dict[str, Any]]:
    return compute_retry_summary(load_events(events_path))
