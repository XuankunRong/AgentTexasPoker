import os
from pathlib import Path
from typing import Any, Dict, List

from holdem.agents import LLMAgent
from holdem.providers.factory import build_llm_client


def build_agent(player_cfg: Dict[str, Any]):
    name = player_cfg["name"]
    ptype = player_cfg.get("type", "llm").lower()

    if ptype != "llm":
        raise ValueError(
            f"Unsupported player type '{ptype}' for {name}. "
            "This public repository only supports LLM agents."
        )

    api_key_env = player_cfg.get("api_key_env")
    if not api_key_env:
        raise ValueError(f"Missing api_key_env for LLM player {name}")

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise EnvironmentError(
            f"Missing environment variable {api_key_env} for player {name}"
        )

    client = build_llm_client(
        provider=player_cfg.get("provider", "openai"),
        model=player_cfg["model"],
        api_key=api_key,
        base_url=player_cfg.get("base_url"),
        extra_body=player_cfg.get("extra_body"),
        system_prompt=player_cfg.get("system_prompt"),
        timeout_sec=player_cfg.get("timeout_sec", 120),
    )

    return LLMAgent(
        name=name,
        client=client,
        max_retries=player_cfg.get("max_retries", 60),
    )


def load_config(path: str | Path) -> Dict[str, Any]:
    import json

    p = Path(path)
    return json.loads(p.read_text())


def build_agents_from_config(cfg: Dict[str, Any]) -> List:
    player_cfgs = cfg.get("players", [])
    return [build_agent(pc) for pc in player_cfgs]
