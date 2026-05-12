from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from holdem.analytics import compute_retry_summary_from_file, compute_risk_metrics, load_events
from holdem.bootstrap import build_agent, load_json
from holdem.engine import HoldemEngine
from holdem.live_logger import LiveLogger


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)
        f.write("\n")


def _resume_state(existing_events: list[dict[str, Any]], seats: list[tuple[str, Any]]) -> tuple[int, int]:
    last_hand_id = 0
    last_dealer_name = None
    for event in existing_events:
        hand_id = int(event.get("hand_id", 0) or 0)
        last_hand_id = max(last_hand_id, hand_id)
        if event.get("type") == "hand_start" and event.get("dealer"):
            last_dealer_name = str(event["dealer"])
    seat_names = [name for name, _ in seats]
    dealer_idx = -1
    if last_dealer_name in seat_names:
        dealer_idx = seat_names.index(last_dealer_name)
    return last_hand_id, dealer_idx


def main() -> None:
    parser = argparse.ArgumentParser(description="Texas Hold'em fixed-blind multi-agent simulator")
    parser.add_argument(
        "--config",
        type=str,
        default="",
        help="Path to simulation config JSON",
    )
    parser.add_argument("--hands", type=int, default=None, help="Override hand count")
    parser.add_argument("--seed", type=int, default=None, help="PRNG seed")
    parser.add_argument("--verbose", action="store_true", help="Print per-hand results")
    parser.add_argument(
        "--log-root",
        type=str,
        default=None,
        help="Directory root for real-time logs (default: outputs/simulation_logs)",
    )
    parser.add_argument(
        "--resume-run-dir",
        type=str,
        default=None,
        help="Append additional hands to an existing run directory",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default=None,
        help="Custom output folder name under log root for a new run",
    )
    args = parser.parse_args()

    resume_run_dir = Path(args.resume_run_dir).resolve() if args.resume_run_dir else None
    if resume_run_dir is not None and args.run_name:
        raise ValueError("--run-name cannot be used together with --resume-run-dir")
    if resume_run_dir is not None:
        meta_path = resume_run_dir / "run_meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Missing run_meta.json in {resume_run_dir}")
        existing_meta = load_json(meta_path)
        if not args.config or args.config == parser.get_default("config"):
            meta_cfg = str(existing_meta.get("config_path", "")).strip()
            if meta_cfg:
                args.config = meta_cfg

    cfg = load_json(Path(args.config))
    experiment_cfg = cfg.get("experiment", {})
    experiment_id = str(experiment_cfg.get("id", "adhoc")).strip() or "adhoc"
    experiment_mode = str(experiment_cfg.get("mode", "continuous")).strip() or "continuous"
    table_cfg = cfg.get("table", {})
    players_cfg = cfg.get("players", [])
    if len(players_cfg) < 2:
        raise ValueError("Need at least 2 players in config")

    seats = [(p["name"], build_agent(p)) for p in players_cfg]
    default_log_root = Path("outputs") / experiment_id / "simulation_logs"
    additional_hands = int(args.hands if args.hands is not None else int(cfg.get("hands", 100)))
    existing_events: list[dict[str, Any]] = []
    existing_completed_hands = 0
    existing_last_hand_id = 0
    existing_dealer_idx = -1
    if resume_run_dir is not None:
        existing_events = load_events(resume_run_dir / "events.jsonl")
        existing_completed_hands = sum(1 for e in existing_events if e.get("type") == "hand_end")
        existing_last_hand_id, existing_dealer_idx = _resume_state(existing_events, seats)
    logger = LiveLogger(
        root_dir=args.log_root or str(default_log_root),
        run_meta={
            "config_path": str(Path(args.config).resolve()),
            "experiment_id": experiment_id,
            "experiment_mode": experiment_mode,
            "hands_target": existing_completed_hands + additional_hands,
            "seed": args.seed,
        },
        existing_run_dir=str(resume_run_dir) if resume_run_dir is not None else None,
        run_name=args.run_name,
    )
    print(f"Live log dir: {logger.run_dir}")
    print(f"Experiment: {experiment_id} ({experiment_mode})")
    if resume_run_dir is not None:
        print(f"Resuming from: {resume_run_dir}")
        print(f"Existing completed hands: {existing_completed_hands}")
        print(f"Appending hands: {additional_hands}")


    observed_events: list[dict[str, Any]] = list(existing_events)
    current_metrics: dict[str, dict[str, Any]] = {}

    def event_sink(event: dict[str, Any]) -> None:
        nonlocal current_metrics
        logger.log_event(event)
        observed_events.append(event)

        if event.get("type") == "hand_end":
            current_metrics = compute_risk_metrics(
                observed_events,
                seed=(args.seed if args.seed is not None else 7),
            )
            metrics_payload = {
                "type": "risk_metrics_update",
                "hand_id": int(event.get("hand_id", 0) or 0),
                "metrics": current_metrics,
            }
            logger.log_event(metrics_payload)
            observed_events.append(metrics_payload)
            _write_json(Path(logger.run_dir) / "risk_metrics.json", {"players": current_metrics})

    engine = HoldemEngine(
        seats=seats,
        starting_stack=int(table_cfg.get("starting_stack", 1000)),
        starting_stacks={
            str(player_cfg.get("name")): int(player_cfg.get("starting_stack"))
            for player_cfg in players_cfg
            if player_cfg.get("starting_stack") is not None
        },
        small_blind=int(table_cfg.get("small_blind", 5)),
        big_blind=int(table_cfg.get("big_blind", 10)),
        max_raises_per_street=int(table_cfg.get("max_raises_per_street", 3)),
        seed=args.seed,
        event_sink=event_sink,
        reset_stacks_each_hand=(experiment_mode == "independent_hands"),
    )
    if resume_run_dir is not None:
        engine.hand_id = existing_last_hand_id
        engine.dealer_idx = existing_dealer_idx

    hand_count = additional_hands
    results = engine.play(hand_count)

    if not current_metrics:
        current_metrics = compute_risk_metrics(
            observed_events,
            seed=(args.seed if args.seed is not None else 7),
        )
        _write_json(Path(logger.run_dir) / "risk_metrics.json", {"players": current_metrics})

    if args.verbose:
        for r in results:
            way = "showdown" if r.showdown else "no-showdown"
            print(f"hand={r.hand_id:03d} winners={','.join(r.winners)} pot={r.pot} {way}")

    print("\n=== Summary ===")
    print(f"Hands played: {len(results)}")
    stacks = engine.stacks()
    for name, stack in sorted(stacks.items(), key=lambda x: x[1], reverse=True):
        win_count = engine.hands_won.get(name, 0)
        print(f"{name:12s} stack={stack:5d} hands_won={win_count}")
    retry_summary = compute_retry_summary_from_file(Path(logger.run_dir) / "events.jsonl")
    retry_summary_path = Path(logger.run_dir) / "retry_summary.json"
    _write_json(retry_summary_path, {"players": retry_summary})
    print(f"\nRisk metrics: {Path(logger.run_dir) / 'risk_metrics.json'}")
    print(f"Retry summary: {retry_summary_path}")


if __name__ == "__main__":
    main()
