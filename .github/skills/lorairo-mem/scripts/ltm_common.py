#!/usr/bin/env python3
"""Common utilities for LoRAIro LTM scripts.

認証情報はスキルディレクトリの .env ファイルから自動読み込みし、
環境変数にセットします。既に環境変数が設定されている場合はそちらが優先されます。
Moltbot Gateway経由でNotion APIにアクセス（プロキシモード）。
フォールバックとして直接Notion APIアクセスも可能。
"""

import json
import os
from pathlib import Path
import sys
import urllib.request


def _load_dotenv() -> None:
    """スキルディレクトリの .env ファイルから環境変数を読み込む。

    既に環境変数が設定されている場合は上書きしない。
    .env ファイルが存在しない場合は何もしない。
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            # 既存の環境変数を上書きしない
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

NOTION_VERSION = "2025-09-03"
NOTION_API = "https://api.notion.com/v1"
GATEWAY_URL = os.environ.get("LORAIRO_MEM_GATEWAY_URL", "http://host.docker.internal:18789")

# LoRAIro-Long-Term Memory (Shared)
DATA_SOURCE_ID = "2f544994-92c3-80d4-a975-000b5fcf09e9"
DATABASE_ID = "2f544994-92c3-8040-9666-ea28223daac6"

DEFAULT_PAGE_SIZE = 10


def get_gateway_token() -> str:
    """Gateway API認証トークンを取得（GW_TOKEN 専用）。

    /v1/responses や /notion/v1 プロキシエンドポイント用。
    Webhook (/hooks/*) には get_hook_token() を使用すること。
    """
    token = os.environ.get("GW_TOKEN")
    if not token:
        raise SystemExit("Missing token: set GW_TOKEN in the environment.")
    return token


def get_hook_token() -> str:
    """Webhook認証トークンを取得（HOOK_TOKEN 専用）。

    /hooks/lorairo-memory エンドポイント用。
    GW_TOKEN とは認証スコープが異なるため、必ず HOOK_TOKEN を使用する。
    """
    token = os.environ.get("HOOK_TOKEN")
    if not token:
        raise SystemExit("Missing token: set HOOK_TOKEN in the environment.")
    return token


def get_notion_key() -> str | None:
    """Notion API Key を取得（オプション、直接アクセス用）"""
    key = os.environ.get("NOTION_API_KEY")
    if key:
        return key
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


def query_via_responses(prompt: str, model: str = "openai-codex/gpt-4.1") -> str:
    """Open Response API経由でNotion LTMを検索する。

    GatewayのLLMがNotionデータソースを参照して回答を返す。

    Args:
        prompt: 検索プロンプト（自然言語）。
        model: 使用するモデルID。

    Returns:
        レスポンスのテキスト内容。
    """
    token = get_gateway_token()
    url = f"{GATEWAY_URL}/v1/responses"
    payload = {
        "model": model,
        "input": prompt,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body) if body else {}
            # Open Response APIの応答からテキストを抽出
            # 形式: {"output": [{"type": "message", "content": [{"type": "output_text", "text": "..."}]}]}
            output = result.get("output", [])
            for item in output:
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            return content.get("text", "")
                # フラット形式のフォールバック
                if item.get("type") == "output_text":
                    return item.get("text", "")
            # 構造が不明な場合はraw JSONを返す
            return json.dumps(result, ensure_ascii=False, indent=2)
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Response API error (HTTP {e.code}): {msg}")


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


def out_text(text: str):
    """テキスト応答をそのまま出力する。"""
    sys.stdout.write(text)
    sys.stdout.write("\n")
