import argparse
import json
import sys
import uuid

import requests


DEFAULT_QA_PROMPTS = [
    "青岚超净蒸汽拖洗一体机适合什么家庭用？跟普通拖把的区别是什么？",
    "这款拖洗机下单后多久发货？坏了怎么保修？",
]
DEFAULT_SCRIPT_PROMPT = "帮我来一段促单话术，强调库存紧张和当前优惠节奏。"
DEFAULT_ANALYST_PROMPT = "帮我生成本场直播复盘报告，重点总结高频问题、未解决问题和优化建议。"
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
    parser = argparse.ArgumentParser(description="Real HTTP smoke test for AnalystAgent.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--username", default="analyst_tester", help="Login username")
    parser.add_argument("--password", default="demo", help="Login password")
    parser.add_argument("--role", default="operator", help="Login role, should be operator or admin")
    parser.add_argument("--product-id", default="SKU-1", help="Current product ID")
    parser.add_argument("--live-stage", default="closing", help="Live stage")
    parser.add_argument("--script-style", default="促销型", help="Script style for seed script message")
    parser.add_argument("--hot-keywords", default="库存,优惠,限时", help="Comma-separated hot keywords")
    parser.add_argument(
        "--live-offer-snapshot-json",
        default=json.dumps(DEFAULT_LIVE_OFFER_SNAPSHOT, ensure_ascii=False),
        help="JSON string for live_offer_snapshot",
    )
    parser.add_argument(
        "--qa-prompts-json",
        default=json.dumps(DEFAULT_QA_PROMPTS, ensure_ascii=False),
        help="JSON array of QA prompts used to seed history",
    )
    parser.add_argument("--script-prompt", default=DEFAULT_SCRIPT_PROMPT, help="Seed script prompt")
    parser.add_argument("--analyst-prompt", default=DEFAULT_ANALYST_PROMPT, help="Final analyst prompt")
    parser.add_argument("--session-id", default="", help="Optional fixed session ID")
    parser.add_argument("--health-timeout", type=float, default=5.0, help="Health check read timeout in seconds")
    parser.add_argument("--login-timeout", type=float, default=15.0, help="Login read timeout in seconds")
    parser.add_argument("--chat-timeout", type=float, default=180.0, help="Chat stream read timeout in seconds")
    return parser.parse_args()


def check_health(base_url: str, timeout_s: float) -> None:
    try:
        response = requests.get(f"{base_url}/health", timeout=(5, timeout_s))
        response.raise_for_status()
    except requests.exceptions.ReadTimeout as exc:
        raise RuntimeError(f"/health timed out after {timeout_s}s") from exc
    except Exception as exc:
        raise RuntimeError(f"/health failed: {exc}") from exc


def login(base_url: str, username: str, password: str, role: str, timeout_s: float) -> str:
    try:
        response = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password, "role": role},
            timeout=(5, timeout_s),
        )
        response.raise_for_status()
    except requests.exceptions.ReadTimeout as exc:
        raise RuntimeError(f"/api/v1/auth/login timed out after {timeout_s}s") from exc
    except Exception as exc:
        raise RuntimeError(f"/api/v1/auth/login failed: {exc}") from exc
    return response.json()["data"]["access_token"]


def parse_json_object(raw: str, arg_name: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid {arg_name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{arg_name} must decode to a JSON object")
    return payload


def parse_json_array(raw: str, arg_name: str) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid {arg_name}: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"{arg_name} must decode to a JSON array")
    return [str(item).strip() for item in payload if str(item).strip()]


def stream_chat(
    base_url: str,
    token: str,
    payload: dict,
    timeout_s: float,
) -> tuple[str, dict]:
    try:
        response = requests.post(
            f"{base_url}/api/v1/chat/stream",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            stream=True,
            timeout=(5, timeout_s),
        )
        response.raise_for_status()
    except requests.exceptions.ReadTimeout as exc:
        raise RuntimeError(f"/api/v1/chat/stream timed out after {timeout_s}s") from exc
    except Exception as exc:
        raise RuntimeError(f"/api/v1/chat/stream failed: {exc}") from exc

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


def send_seed_request(
    *,
    base_url: str,
    token: str,
    session_id: str,
    user_input: str,
    product_id: str,
    live_stage: str,
    timeout_s: float,
    script_style: str | None = None,
    hot_keywords: list[str] | None = None,
    live_offer_snapshot: dict | None = None,
) -> dict:
    payload = {
        "session_id": session_id,
        "user_input": user_input,
        "current_product_id": product_id,
        "live_stage": live_stage,
        "script_style": script_style,
        "hot_keywords": hot_keywords or [],
        "live_offer_snapshot": live_offer_snapshot or {},
    }
    print(f"\n=== Sending seed request: {user_input}")
    _, final_payload = stream_chat(base_url, token, payload, timeout_s)
    return final_payload


def validate_seed_payload(final_payload: dict, expected_intent: str) -> None:
    if final_payload["intent"] != expected_intent:
        raise AssertionError(f"Expected seed intent={expected_intent}, got {final_payload['intent']!r}")
    if final_payload["guardrail_pass"] is not True:
        raise AssertionError(f"Seed request guardrail did not pass for intent={expected_intent}")


def validate_analyst_payload(final_payload: dict) -> None:
    if final_payload["intent"] != "analyst":
        raise AssertionError(f"Expected intent=analyst, got {final_payload['intent']!r}")
    if final_payload["guardrail_pass"] is not True:
        raise AssertionError("Guardrail did not pass this AnalystAgent response")

    message = final_payload["message"]
    metadata = message["metadata"]

    if message["agent_name"] != "analyst":
        raise AssertionError(f"Expected agent_name=analyst, got {message['agent_name']!r}")
    if not message["content"].strip():
        raise AssertionError("Assistant content is empty")

    report = metadata.get("analyst_report")
    if not isinstance(report, dict) or not report:
        raise AssertionError("Missing analyst_report in assistant metadata")
    if report.get("total_messages", 0) <= 0:
        raise AssertionError("analyst_report.total_messages should be > 0")
    if not isinstance(report.get("top_questions", []), list):
        raise AssertionError("analyst_report.top_questions should be a list")
    if not isinstance(report.get("suggestions", []), list) or not report.get("suggestions"):
        raise AssertionError("analyst_report.suggestions should be a non-empty list")


def main() -> int:
    args = parse_args()
    session_id = args.session_id or f"analyst-agent-smoke-{uuid.uuid4().hex[:8]}"
    hot_keywords = [item.strip() for item in args.hot_keywords.split(",") if item.strip()]
    live_offer_snapshot = parse_json_object(args.live_offer_snapshot_json, "--live-offer-snapshot-json")
    qa_prompts = parse_json_array(args.qa_prompts_json, "--qa-prompts-json")

    print(f"Session ID: {session_id}")
    print(f"Base URL: {args.base_url}")

    try:
        check_health(args.base_url, args.health_timeout)
        token = login(args.base_url, args.username, args.password, args.role, args.login_timeout)

        for prompt in qa_prompts:
            qa_payload = send_seed_request(
                base_url=args.base_url,
                token=token,
                session_id=session_id,
                user_input=prompt,
                product_id=args.product_id,
                live_stage="pitch",
                timeout_s=args.chat_timeout,
            )
            validate_seed_payload(qa_payload, "qa")

        script_payload = send_seed_request(
            base_url=args.base_url,
            token=token,
            session_id=session_id,
            user_input=args.script_prompt,
            product_id=args.product_id,
            live_stage=args.live_stage,
            timeout_s=args.chat_timeout,
            script_style=args.script_style,
            hot_keywords=hot_keywords,
            live_offer_snapshot=live_offer_snapshot,
        )
        validate_seed_payload(script_payload, "script")

        print(f"\n=== Sending analyst request: {args.analyst_prompt}")
        _, analyst_payload = stream_chat(
            args.base_url,
            token,
            {
                "session_id": session_id,
                "user_input": args.analyst_prompt,
                "current_product_id": args.product_id,
                "live_stage": args.live_stage,
            },
            args.chat_timeout,
        )
        validate_analyst_payload(analyst_payload)
    except Exception as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1

    print("\nPASS: AnalystAgent real API smoke test succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
