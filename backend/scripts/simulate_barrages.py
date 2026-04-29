import argparse
import random
import time
from datetime import datetime

import requests


SAMPLE_TEXTS = [
    "1号链接还有吗？",
    "这款适合什么家庭使用？",
    "运费谁出？",
    "有色差吗？",
    "能不能便宜点",
    "多久发货？",
    "现在下单有什么赠品？",
    "这款和普通拖把区别是什么？",
    "库存还多吗？",
    "售后怎么保修？",
]


def parse_args():
    parser = argparse.ArgumentParser(description="向 LiveAgent Studio 注入模拟弹幕流")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端服务地址")
    parser.add_argument("--session-id", default="studio-live-room-001", help="直播会话 ID")
    parser.add_argument("--username", default="demo-operator", help="用于登录的直播工作人员账号")
    parser.add_argument("--password", default="demo", help="登录密码")
    parser.add_argument("--role", default="operator", help="登录角色")
    parser.add_argument("--product-id", default="", help="当前直播商品 ID，不传则表示未设置商品")
    parser.add_argument("--live-stage", default="intro", help="当前直播阶段")
    parser.add_argument("--interval", type=float, default=1.5, help="两条弹幕之间的秒数")
    parser.add_argument("--online-viewers", type=int, default=12450, help="模拟在线人数")
    parser.add_argument("--conversion-rate", type=float, default=3.24, help="模拟转化率")
    parser.add_argument("--interaction-rate", type=float, default=7.8, help="模拟互动率")
    return parser.parse_args()


def login(base_url: str, username: str, password: str, role: str) -> str:
    response = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["data"]["access_token"]


def main():
    args = parse_args()
    token = login(args.base_url, args.username, args.password, args.role)
    headers = {"Authorization": f"Bearer {token}"}

    print(f"simulate session={args.session_id} product={args.product_id} stage={args.live_stage}")
    print("按 Ctrl+C 停止注入")

    counter = 0
    try:
        while True:
            counter += 1
            text = random.choice(SAMPLE_TEXTS)
            payload = {
                "session_id": args.session_id,
                "display_name": f"User_{random.randint(100, 999)}",
                "user_id": f"user-{random.randint(1000, 9999)}",
                "text": text,
                "source": "simulator",
                "current_product_id": args.product_id,
                "live_stage": args.live_stage,
                "online_viewers": args.online_viewers + random.randint(-120, 120),
                "conversion_rate": max(args.conversion_rate + random.uniform(-0.2, 0.2), 0),
                "interaction_rate": max(args.interaction_rate + random.uniform(-1, 1), 0),
                "metadata": {"sequence": counter},
                "created_at": datetime.utcnow().isoformat(),
            }
            response = requests.post(
                f"{args.base_url}/api/v1/live/barrages/ingest",
                json=payload,
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            print(f"[{counter:04d}] {payload['display_name']}: {text}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n已停止模拟弹幕注入")


if __name__ == "__main__":
    main()
