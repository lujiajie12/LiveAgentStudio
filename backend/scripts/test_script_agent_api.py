import argparse
import json
import sys
import uuid

import requests


DEFAULT_USER_INPUT = "帮我来一段促单话术，强调库存紧张和当前优惠节奏。"
DEFAULT_SCRIPT_STYLE = "促销型"
DEFAULT_HOT_KEYWORDS = "库存,优惠,限时"
DEFAULT_LIVE_OFFER_SNAPSHOT = {
    "display_stock": 92,
    "display_unit": "套",
    "stock_label": "库存紧张",
    "current_price": "89元",
    "original_price": "149元",
    "countdown_seconds": 180,
    "coupon_summary": "下单立减20元",
    "gift_summary": "赠清洁布1份",
    "activity_summary": "直播间专属优惠进行中",
    "source": "yellow_cart",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real HTTP smoke test for ScriptAgent.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--username", default="script_tester", help="Login username")
    parser.add_argument("--password", default="demo", help="Login password")
    parser.add_argument("--role", default="operator", help="Login role")
    parser.add_argument("--user-input", default=DEFAULT_USER_INPUT, help="Prompt sent to ScriptAgent")
    parser.add_argument("--product-id", default="SKU-1", help="Current product ID")
    parser.add_argument("--live-stage", default="closing", help="Live stage")
    parser.add_argument("--script-style", default=DEFAULT_SCRIPT_STYLE, help="Script style")
    parser.add_argument("--hot-keywords", default=DEFAULT_HOT_KEYWORDS, help="Comma-separated hot keywords")
    parser.add_argument(
        "--live-offer-snapshot-json",
        default=json.dumps(DEFAULT_LIVE_OFFER_SNAPSHOT, ensure_ascii=False),
        help="JSON string for live_offer_snapshot",
    )
    parser.add_argument("--session-id", default="", help="Optional fixed session ID")
    parser.add_argument("--health-timeout", type=float, default=5.0, help="Health check read timeout in seconds")
    parser.add_argument("--login-timeout", type=float, default=15.0, help="Login read timeout in seconds")
    parser.add_argument("--chat-timeout", type=float, default=120.0, help="Chat stream read timeout in seconds")
    return parser.parse_args()


def check_health(base_url: str, timeout_s: float) -> None:
    try:
        response = requests.get(
            f"{base_url}/health",
            timeout=(5, timeout_s),
        )
        response.raise_for_status()
    except requests.exceptions.ReadTimeout as exc:
        raise RuntimeError(f"/health timed out after {timeout_s}s, backend may be hung or not ready") from exc
    except Exception as exc:
        raise RuntimeError(f"/health failed: {exc}") from exc


def login(base_url: str, username: str, password: str, role: str, timeout_s: float) -> str:
    try:
        response = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={
                "username": username,
                "password": password,
                "role": role,
            },
            timeout=(5, timeout_s),
        )
        response.raise_for_status()
    except requests.exceptions.ReadTimeout as exc:
        raise RuntimeError(f"/api/v1/auth/login timed out after {timeout_s}s") from exc
    except Exception as exc:
        raise RuntimeError(f"/api/v1/auth/login failed: {exc}") from exc

    payload = response.json()
    return payload["data"]["access_token"]


def stream_chat(
    base_url: str,
    token: str,
    session_id: str,
    user_input: str,
    product_id: str,
    live_stage: str,
    script_style: str,
    hot_keywords: list[str],
    live_offer_snapshot: dict,
    timeout_s: float,
) -> tuple[str, dict]:
    try:
        response = requests.post(
            f"{base_url}/api/v1/chat/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "session_id": session_id,
                "user_input": user_input,
                "current_product_id": product_id,
                "live_stage": live_stage,
                "script_style": script_style,
                "hot_keywords": hot_keywords,
                "live_offer_snapshot": live_offer_snapshot,
            },
            stream=True,
            timeout=(5, timeout_s),
        )
        response.raise_for_status()
    except requests.exceptions.ReadTimeout as exc:
        raise RuntimeError(f"/api/v1/chat/stream timed out after {timeout_s}s") from exc
    except Exception as exc:
        raise RuntimeError(f"/api/v1/chat/stream failed: {exc}") from exc

    print(f"HTTP {response.status_code}")

    current_event = None
    final_payload = None
    all_lines: list[str] = []

    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = str(raw_line)
            all_lines.append(line)
            print(line)
            if line.startswith("event: "):
                current_event = line[len("event: ") :]
                continue
            if current_event == "final" and line.startswith("data: "):
                final_payload = json.loads(line[len("data: ") :])
    except requests.exceptions.ReadTimeout as exc:
        raise RuntimeError(f"SSE stream read timed out after {timeout_s}s") from exc

    if final_payload is None:
        raise AssertionError("No final SSE payload received from /chat/stream")

    return "\n".join(all_lines), final_payload


def validate_script_result(final_payload: dict) -> None:
    if final_payload["intent"] != "script":
        raise AssertionError(f"Expected intent=script, got {final_payload['intent']!r}")

    if final_payload["guardrail_pass"] is not True:
        raise AssertionError("Guardrail did not pass this ScriptAgent response")

    message = final_payload["message"]
    metadata = message["metadata"]

    if message["agent_name"] != "script":
        raise AssertionError(f"Expected agent_name=script, got {message['agent_name']!r}")

    if not message["content"].strip():
        raise AssertionError("Assistant content is empty")

    if not metadata.get("script_type"):
        raise AssertionError("Missing script_type in assistant metadata")

    if not metadata.get("script_tone"):
        raise AssertionError("Missing script_tone in assistant metadata")

    candidates = metadata.get("script_candidates", [])
    if not isinstance(candidates, list) or not candidates:
        raise AssertionError("Missing script_candidates in assistant metadata")


def parse_snapshot(snapshot_json: str) -> dict:
    try:
        payload = json.loads(snapshot_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid --live-offer-snapshot-json: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("--live-offer-snapshot-json must decode to a JSON object")
    return payload


def main() -> int:
    args = parse_args()
    session_id = args.session_id or f"script-agent-smoke-{uuid.uuid4().hex[:8]}"
    hot_keywords = [item.strip() for item in args.hot_keywords.split(",") if item.strip()]
    live_offer_snapshot = parse_snapshot(args.live_offer_snapshot_json)

    print(f"Session ID: {session_id}")
    print(f"Base URL: {args.base_url}")

    try:
        check_health(args.base_url, args.health_timeout)
        token = login(args.base_url, args.username, args.password, args.role, args.login_timeout)
        _, final_payload = stream_chat(
            base_url=args.base_url,
            token=token,
            session_id=session_id,
            user_input=args.user_input,
            product_id=args.product_id,
            live_stage=args.live_stage,
            script_style=args.script_style,
            hot_keywords=hot_keywords,
            live_offer_snapshot=live_offer_snapshot,
            timeout_s=args.chat_timeout,
        )
        validate_script_result(final_payload)
    except Exception as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1

    print("\nPASS: ScriptAgent real API smoke test succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
