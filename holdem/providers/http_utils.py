from __future__ import annotations

import json
import os
import subprocess
from urllib import request
from urllib.parse import urlparse


def _is_soruxgpt_url(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return hostname == "ai.soruxgpt.com" or hostname.endswith(".soruxgpt.com")


def _post_json_with_curl(url: str, payload: dict, headers: dict[str, str], timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False)
    cmd = [
        "curl",
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        str(int(max(timeout, 1))),
        "--request",
        "POST",
        url,
        "--header",
        "Content-Type: application/json",
    ]
    for key, value in headers.items():
        cmd.extend(["--header", f"{key}: {value}"])
    cmd.extend(["--data-binary", body])

    env = os.environ.copy()
    for key in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
    ):
        env.pop(key, None)
    hostname = urlparse(url).hostname or ""
    if hostname:
        env["NO_PROXY"] = hostname
        env["no_proxy"] = hostname

    proc = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    raw = proc.stdout.strip()
    return json.loads(raw)


def post_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 30.0) -> dict:
    if _is_soruxgpt_url(url):
        return _post_json_with_curl(url, payload, headers, timeout)

    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url=url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)

    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)
