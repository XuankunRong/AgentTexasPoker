from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LiveLogger:
    def __init__(
        self,
        root_dir: str | None = None,
        run_meta: dict[str, Any] | None = None,
        existing_run_dir: str | None = None,
        run_name: str | None = None,
    ) -> None:
        base = Path(root_dir) if root_dir else Path("outputs/simulation_logs")
        if existing_run_dir:
            self.run_dir = Path(existing_run_dir)
        else:
            if run_name:
                self.run_dir = base / run_name
                if self.run_dir.exists():
                    raise FileExistsError(f"Run directory already exists: {self.run_dir}")
            else:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.run_dir = base / f"run_{ts}"
        self.hands_dir = self.run_dir / "hands"
        self._event_seq = 0
        self.hands_dir.mkdir(parents=True, exist_ok=True)
        meta_path = self.run_dir / "run_meta.json"
        meta = {}
        if meta_path.exists():
            try:
                loaded = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    meta.update(loaded)
            except Exception:
                pass
        if not meta:
            meta = {
                "created_at_local": datetime.now().isoformat(),
                "run_dir": str(self.run_dir),
            }
        if isinstance(run_meta, dict):
            meta.update(run_meta)
        self._write_json(meta_path, meta)
        transcript_path = self.run_dir / "transcript.md"
        if not transcript_path.exists():
            self._append_text(transcript_path, "# Simulation Transcript\n\n")

        events_path = self.run_dir / "events.jsonl"
        if events_path.exists():
            try:
                with events_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        raw = line.strip()
                        if not raw:
                            continue
                        obj = json.loads(raw)
                        if isinstance(obj, dict):
                            self._event_seq = max(self._event_seq, int(obj.get("seq", 0) or 0))
            except Exception:
                pass

    def _append_jsonl(self, path: Path, obj: dict[str, Any]) -> None:
        line = json.dumps(obj, ensure_ascii=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _append_text(self, path: Path, text: str) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

    def _write_json(self, path: Path, obj: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

    def _hand_dir(self, hand_id: int) -> Path:
        d = self.hands_dir / f"hand_{hand_id:04d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=True)

    def _render_event_markdown(self, event: dict[str, Any]) -> str:
        event_type = event.get("type")
        hand_id = event.get("hand_id")
        if event_type == "hand_start":
            parts: list[str] = []
            parts.append(f"## Hand {int(hand_id):04d}\n")
            parts.append(f"- Dealer: {event.get('dealer')}\n")
            sb = event.get("small_blind", {})
            bb = event.get("big_blind", {})
            parts.append(
                f"- Blinds: SB {sb.get('player')} {sb.get('amount')} | BB {bb.get('player')} {bb.get('amount')}\n"
            )
            order = event.get("table_order_from_dealer", [])
            pre_order = event.get("preflop_action_order", [])
            positions = event.get("positions_by_player", {}) or {}
            parts.append(f"- Table order: {', '.join(order)}\n")
            parts.append(f"- Preflop action order: {', '.join(pre_order)}\n")
            if positions:
                pos_line = " | ".join(f"{name}:{pos}" for name, pos in positions.items())
                parts.append(f"- Positions: {pos_line}\n")
            parts.append("\n### Hole Cards\n")
            for name, cards in (event.get("hole_cards", {}) or {}).items():
                parts.append(f"- {name}: {' '.join(cards)}\n")
            parts.append("\n")
            return "".join(parts)

        if event_type == "blind_post":
            blind = event.get("blind")
            player = event.get("player")
            position = event.get("player_position")
            amount = event.get("amount")
            pot_after = event.get("pot_after")
            pos = f" ({position})" if position else ""
            return f"- Blind posted: {blind} by {player}{pos}, amount={amount}, pot={pot_after}\n"

        if event_type == "street_start":
            board = event.get("board", []) or []
            board_str = " ".join(board) if board else "-"
            street = event.get("street")
            pot = event.get("pot")
            return f"\n### {street}\n- Board: {board_str}\n- Pot: {pot}\n\n"

        if event_type == "action":
            player = event.get("player")
            position = event.get("player_position")
            final_action = event.get("final_action")
            final_amount = event.get("final_amount")
            to_call = event.get("to_call")
            pot_before = event.get("pot_before")
            pot_after = event.get("pot_after")
            pos = f" [{position}]" if position else ""
            line = (
                f"- {player}{pos}: {final_action}"
                f"{(' ' + str(final_amount)) if final_action in {'call', 'raise'} else ''} "
                f"(to_call={to_call}, pot={pot_before}->{pot_after})\n"
            )
            dialogue = event.get("agent_dialogue")
            if isinstance(dialogue, dict):
                prompt = self._safe_text(dialogue.get("prompt"))
                raw = self._safe_text(dialogue.get("raw_response"))
                err = self._safe_text(dialogue.get("error"))
                retry_attempts = dialogue.get("retry_attempts")
                if prompt:
                    line += "\nPrompt:\n```text\n" + prompt + "\n```\n"
                if isinstance(retry_attempts, list) and retry_attempts:
                    line += "\nRetryAttempts:\n"
                    for attempt in retry_attempts:
                        idx = attempt.get("attempt")
                        aerr = self._safe_text(attempt.get("error"))
                        araw = self._safe_text(attempt.get("raw_response"))
                        line += f"- attempt={idx}"
                        if aerr:
                            line += f" error={aerr}\n"
                        else:
                            line += "\n"
                        if araw:
                            line += "```text\n" + araw + "\n```\n"
                if raw:
                    line += "\nResponse:\n```text\n" + raw + "\n```\n"
                if err:
                    line += "\nError:\n```text\n" + err + "\n```\n"
            decide_error = self._safe_text(event.get("decide_error"))
            if decide_error:
                line += "\nDecideError:\n```text\n" + decide_error + "\n```\n"
            return line

        if event_type == "hand_end":
            result = event.get("result", {}) or {}
            winners = ", ".join(result.get("winners", []) or [])
            pot = result.get("pot")
            showdown = result.get("showdown")
            stacks = event.get("stacks", {}) or {}
            ordered = sorted(stacks.items(), key=lambda kv: kv[1], reverse=True)
            stack_line = " | ".join(f"{k}:{v}" for k, v in ordered)
            return (
                f"\n### Hand Result\n"
                f"- Winners: {winners}\n"
                f"- Pot: {pot}\n"
                f"- Showdown: {showdown}\n"
                f"- Stacks: {stack_line}\n\n---\n\n"
            )

        if event_type == "hand_reflection":
            player = event.get("player")
            net = event.get("net_chip_change")
            think = event.get("thinking_time_sec")
            assess = self._safe_text(event.get("self_assessment"))
            adjust = self._safe_text(event.get("strategy_adjustment"))
            lines = [
                f"\n### Reflection - {player}\n",
                f"- Net Chips: {net}\n",
                f"- Thinking Time: {think}s\n",
                f"- Self Assessment: {assess}\n",
                f"- Strategy Adjustment: {adjust}\n",
            ]
            obs = event.get("opponent_observations")
            if isinstance(obs, dict) and obs:
                lines.append("- Opponent Observations:\n")
                for opp, note in obs.items():
                    lines.append(f"  - {opp}: {self._safe_text(note)}\n")
            raw = self._safe_text(event.get("raw_response"))
            if raw:
                lines.append("\nRawReflectionResponse:\n```text\n" + raw + "\n```\n")
            err = self._safe_text(event.get("error"))
            if err:
                lines.append("\nReflectionError:\n```text\n" + err + "\n```\n")
            return "".join(lines)

        if event_type == "risk_metrics_update":
            metrics = event.get("metrics", {}) or {}
            lines = [
                "\n### Risk Metrics Update\n",
                f"- Hand: {int(hand_id):04d}\n",
            ]
            for player, row in sorted(metrics.items()):
                lines.append(
                    "- {player}: VPIP={vpip} PFR={pfr} AF={af}\n".format(
                        player=player,
                        vpip=row.get("vpip"),
                        pfr=row.get("pfr"),
                        af=row.get("aggression_factor_raw"),
                    )
                )
            lines.append("\n")
            return "".join(lines)

        return ""

    def log_event(self, event: dict[str, Any]) -> None:
        incoming_seq = None
        if "seq" in event:
            try:
                incoming_seq = int(event.get("seq", 0) or 0)
            except Exception:
                incoming_seq = None
        if incoming_seq is None or incoming_seq <= self._event_seq:
            self._event_seq += 1
            rewritten = dict(event)
            if incoming_seq is not None:
                rewritten["orig_seq"] = incoming_seq
            rewritten["seq"] = self._event_seq
            event = rewritten
        else:
            self._event_seq = incoming_seq
        if "ts_utc" not in event:
            event = {
                **event,
                "ts_utc": datetime.now(timezone.utc).isoformat(),
            }
        self._append_jsonl(self.run_dir / "events.jsonl", event)
        global_md = self._render_event_markdown(event)
        if global_md:
            self._append_text(self.run_dir / "transcript.md", global_md)
        hand_id = event.get("hand_id")
        if not isinstance(hand_id, int):
            return
        hand_dir = self._hand_dir(hand_id)
        self._append_jsonl(hand_dir / "events.jsonl", event)
        hand_transcript = hand_dir / "transcript.md"
        if event.get("type") == "hand_start":
            self._append_text(hand_transcript, f"# Hand {hand_id:04d} Transcript\n\n")
        hand_md = self._render_event_markdown(event)
        if hand_md:
            self._append_text(hand_transcript, hand_md)

        event_type = event.get("type")
        if event_type == "hand_start":
            self._write_json(hand_dir / "hand_info.json", event)
        elif event_type == "hand_end":
            self._write_json(hand_dir / "summary.json", event)
        elif event_type == "hand_reflection":
            self._append_jsonl(hand_dir / "reflections.jsonl", event)
        elif event_type == "risk_metrics_update":
            self._write_json(self.run_dir / "risk_metrics.json", {"players": event.get("metrics", {})})
