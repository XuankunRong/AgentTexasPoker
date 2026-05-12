from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from holdem.analytics import compute_retry_summary


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
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
                events.append(obj)
    events.sort(key=lambda e: int(e.get("seq", 0) or 0))
    return events


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_hand_summaries(events: list[dict]) -> list[dict]:
    starts: dict[int, dict] = {}
    summaries: dict[int, dict] = {}
    for event in events:
        hand_id = int(event.get("hand_id", 0) or 0)
        if hand_id <= 0:
            continue
        etype = event.get("type")
        if etype == "hand_start":
            starts[hand_id] = {
                "dealer": event.get("dealer"),
            }
        elif etype == "hand_end":
            result = event.get("result") or {}
            summaries[hand_id] = {
                "handId": hand_id,
                "dealer": (starts.get(hand_id) or {}).get("dealer"),
                "winners": ", ".join(result.get("winners") or []),
                "pot": result.get("pot"),
                "showdown": "showdown" if result.get("showdown") else "no-showdown",
                "board": event.get("community_cards") or [],
            }
    return [summaries[k] for k in sorted(summaries.keys(), reverse=True)]


def _discover_runs(root: Path) -> list[dict]:
    if not root.exists():
        return []
    runs: list[dict] = []
    for p in root.rglob("run_*"):
        if not p.is_dir():
            continue
        if not (p / "events.jsonl").exists():
            continue
        meta = p / "run_meta.json"
        created_at = None
        if meta.exists():
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
                created_at = payload.get("created_at_local")
            except Exception:
                created_at = None
        runs.append(
            {
                "id": str(p.relative_to(root)),
                "path": str(p),
                "created_at_local": created_at,
                "updated_at_epoch": p.stat().st_mtime,
            }
        )
    runs.sort(key=lambda x: str(x["id"]).lower())
    return runs


@dataclass
class DashboardState:
    static_dir: Path
    root_dir: Path
    pinned_run_dir: Path | None = None

    def resolve_run(self, run_id: str | None) -> Path | None:
        if self.pinned_run_dir is not None:
            return self.pinned_run_dir
        runs = _discover_runs(self.root_dir)
        if run_id:
            for run in runs:
                if run["id"] == run_id:
                    return Path(run["path"])
            return None
        if runs:
            return Path(runs[0]["path"])
        return None


class DashboardHandler(SimpleHTTPRequestHandler):
    state: DashboardState

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.state.static_dir), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            if parsed.path in {"/", "/index.html"}:
                self.path = "/index.html"
            return super().do_GET()

        query = parse_qs(parsed.query)
        if parsed.path == "/api/runs":
            runs = _discover_runs(self.state.root_dir)
            return self._send_json({"runs": runs})

        if parsed.path == "/api/status":
            run_id = query.get("run", [None])[0]
            run_dir = self.state.resolve_run(run_id)
            if run_dir is None:
                return self._send_json({"run": None, "error": "no run found"}, status=404)
            return self._send_json(
                {
                    "run": {
                        "id": str(run_dir.relative_to(self.state.root_dir))
                        if self.state.pinned_run_dir is None
                        else str(run_dir),
                        "path": str(run_dir),
                    },
                    "server_time": datetime.now().isoformat(),
                }
            )

        if parsed.path == "/api/events":
            run_id = query.get("run", [None])[0]
            run_dir = self.state.resolve_run(run_id)
            if run_dir is None:
                return self._send_json({"events": [], "max_seq": 0, "error": "run not found"}, status=404)
            since_raw = query.get("since", ["0"])[0]
            try:
                since = int(since_raw)
            except ValueError:
                since = 0
            events = _load_jsonl(run_dir / "events.jsonl")
            selected = [e for e in events if int(e.get("seq", 0) or 0) > since]
            max_seq = int(events[-1].get("seq", 0) or 0) if events else 0
            latest_metrics_event = None
            for event in reversed(events):
                if event.get("type") == "risk_metrics_update":
                    latest_metrics_event = event
                    break
            risk_metrics_payload = _load_json(run_dir / "risk_metrics.json")
            retry_summary_payload = compute_retry_summary(events)
            hand_summaries = _build_hand_summaries(events)
            return self._send_json(
                {
                    "run_id": (
                        str(run_dir.relative_to(self.state.root_dir))
                        if self.state.pinned_run_dir is None
                        else str(run_dir)
                    ),
                    "run_dir": str(run_dir),
                    "events": selected,
                    "max_seq": max_seq,
                    "latest_risk_metrics_event": latest_metrics_event,
                    "risk_metrics": risk_metrics_payload.get("players", {}),
                    "retry_summary": retry_summary_payload,
                    "hand_summaries": hand_summaries,
                }
            )

        return self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)


def main() -> None:
    parser = argparse.ArgumentParser(description="Realtime dashboard for simulation logs")
    parser.add_argument(
        "--root",
        type=str,
        default="outputs",
        help="Root directory to discover run_* logs (recursive)",
    )
    parser.add_argument(
        "--run-dir",
        type=str,
        default=None,
        help="Pin dashboard to a single run directory",
    )
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    static_dir = Path("web/dashboard").resolve()
    if not static_dir.exists():
        raise FileNotFoundError(f"Missing dashboard static files: {static_dir}")

    root_dir = Path(args.root).resolve()
    run_dir = Path(args.run_dir).resolve() if args.run_dir else None
    if run_dir is not None and not run_dir.exists():
        raise FileNotFoundError(f"--run-dir does not exist: {run_dir}")

    state = DashboardState(static_dir=static_dir, root_dir=root_dir, pinned_run_dir=run_dir)
    handler = type("BoundDashboardHandler", (DashboardHandler,), {"state": state})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Dashboard: http://{args.host}:{args.port}")
    if run_dir:
        print(f"Pinned run: {run_dir}")
    else:
        print(f"Run discovery root: {root_dir}")
    server.serve_forever()


if __name__ == "__main__":
    main()
