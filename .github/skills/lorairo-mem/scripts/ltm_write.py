#!/usr/bin/env python3
"""Write a memory via Moltbot webhook.

.env ファイルから自動的にトークンを読み込みます（ltm_common経由）。
"""

import json
import sys
import urllib.request

# ltm_common をインポートすることで .env の自動読み込みが行われる
from ltm_common import get_gateway_token, read_stdin_json, GATEWAY_URL


def main() -> None:
    payload = read_stdin_json()
    if not payload:
        raise SystemExit("Provide JSON on stdin.")
    token = get_gateway_token()

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{GATEWAY_URL}/hooks/lorairo-memory",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        sys.stdout.write(body if body else "{}")
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
