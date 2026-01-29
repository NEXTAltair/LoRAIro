#!/usr/bin/env python3
"""Common utilities for LoRAIro LTM scripts.

認証情報は ~/.clawdbot/clawdbot.json から取得。
Moltbot Gateway経由でNotion APIにアクセス（プロキシモード）。
フォールバックとして直接Notion APIアクセスも可能。
"""

import json
import os
import sys
import urllib.request

NOTION_VERSION = "2025-09-03"
NOTION_API = "https://api.notion.com/v1"
GATEWAY_URL = "http://host.docker.internal:18789"

# LoRAIro-Long-Term Memory (Shared)
DATA_SOURCE_ID = "2f544994-92c3-80d4-a975-000b5fcf09e9"
DATABASE_ID = "2f544994-92c3-8040-9666-ea28223daac6"

DEFAULT_PAGE_SIZE = 10


def read_clawdbot_config() -> dict:
    """~/.clawdbot/clawdbot.json から設定を読み込む"""
    path = os.path.expanduser("~/.clawdbot/clawdbot.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"clawdbot config not found: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in clawdbot config: {e}")


def get_gateway_token() -> str:
    """Gateway認証トークンを取得（hooks.token優先、gateway.auth.tokenフォールバック）"""
    config = read_clawdbot_config()
    token = config.get("hooks", {}).get("token")
    if not token:
        token = config.get("gateway", {}).get("auth", {}).get("token")
    if not token:
        raise SystemExit("No token found in clawdbot config (hooks.token or gateway.auth.token)")
    return token


def get_notion_key() -> str | None:
    """Notion API Key を取得（オプション、直接アクセス用）"""
    # まず clawdbot.json から
    try:
        config = read_clawdbot_config()
        key = config.get("notion", {}).get("api_key")
        if key:
            return key
    except SystemExit:
        pass

    # フォールバック: 旧形式の設定ファイル
    path = os.path.expanduser("~/.config/notion/api_key")
    try:
        with open(path, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass

    return None


def http_json(method: str, path: str, payload=None):
    """Gateway経由でNotion APIにアクセス。フォールバックで直接アクセス。"""
    # まずGateway経由を試行
    try:
        return _http_json_gateway(method, path, payload)
    except Exception as gw_err:
        # Gateway失敗時は直接Notion APIにフォールバック
        notion_key = get_notion_key()
        if notion_key:
            try:
                return _http_json_direct(method, path, payload, notion_key)
            except Exception as direct_err:
                raise SystemExit(f"Both Gateway and direct Notion access failed.\nGateway: {gw_err}\nDirect: {direct_err}")
        raise SystemExit(f"Gateway access failed and no Notion API key available: {gw_err}")


def _http_json_gateway(method: str, path: str, payload=None):
    """Moltbot Gateway経由でNotion APIにアクセス"""
    token = get_gateway_token()
    # Gateway経由のNotionプロキシエンドポイント
    url = f"{GATEWAY_URL}/notion/v1{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else None


def _http_json_direct(method: str, path: str, payload=None, api_key: str = None):
    """直接Notion APIにアクセス（フォールバック用）"""
    if not api_key:
        api_key = get_notion_key()
    if not api_key:
        raise SystemExit("Notion API key not available")

    url = f"{NOTION_API}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Notion HTTP {e.code}: {msg}")


def read_stdin_json():
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON on stdin: {e}")


def out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
