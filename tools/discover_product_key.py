#!/usr/bin/env python3
"""
discover_product_key.py — 连接机器人 WebSocket，自动从广播帧提取 product_key。

用法：
    python3 tools/discover_product_key.py [IP] [PORT]
    python3 tools/discover_product_key.py <robot_ip>
    python3 tools/discover_product_key.py <robot_ip> 9002

机器人开机后，直接连接 ws://IP:9002，监听广播帧。
广播 topic 格式：/{product_key}/{device_id}/status/...
脚本解析 topic 并打印 product_key 和 device_id。
"""

import asyncio
import sys
import re

try:
    import websockets
except ImportError:
    print("需要安装 websockets：pip3 install websockets")
    sys.exit(1)

DEFAULT_HOST = ""
DEFAULT_PORT = 9002

# 已知 product_key 列表（用于发送唤醒帧）
KNOWN_PRODUCT_KEYS = [
    "QoEsI5qYXO",  # AX12 — Narwal Flow
    "DrzDKQ0MU8",  # CX4  — Freo Z10 Ultra
    "CNbforyZWI",  # AX15 — Freo X10 Pro
    "BYWBPqSxeC",  # CX7  — Freo Z Ultra
    "LnugwMG9ss",  # AX18 — Freo X Ultra
    "5OMbqk58Sc",  # AX19
    "tPQJmoIbEC",  # AX6
    "HgArZ7KuJL",  # AX7
    "Uuug39n0fD",  # AX8
    "E9Q8aDzUbp",  # AX17
    "jI5rHi4mKa",  # AX24
    "UuTSLsMce4",  # AX25
    "qV6BujoYLz",  # AX26
    "88OLXLpkjT",  # BX4
    "3rIGshGNAj",  # BX4/Y1 alternate
    "7sSZZ4XfTI",  # CX2
    "OlkUn3oUCu",  # CX3/CX3Pure
    "mvlduyye85",  # X30
    "pcbfh2ldvx",  # X31
    "EHf6cRNRGT",  # J4/J4Pure
    "6NjIDYxBXb",  # J4Lite
    "hEA7OEshlx",  # J5
    "cUlfJN5JYP",  # Unknown
]


def build_raw_frame(topic: str, payload: bytes = b"") -> bytes:
    """构建最小化 Narwal WebSocket 帧。"""
    topic_bytes = topic.encode("utf-8")
    frame = bytearray()
    frame.append(0x01)                      # frame type
    frame.append(len(topic_bytes) + 2)      # header byte
    frame.append(0x22)                      # protobuf field 4 tag
    frame.append(len(topic_bytes))          # topic length
    frame.extend(topic_bytes)
    frame.extend(payload)
    return bytes(frame)


def parse_topic_from_frame(data: bytes) -> str | None:
    """从原始帧数据提取 topic 字符串，失败返回 None。"""
    if len(data) < 4:
        return None
    if data[0] != 0x01:
        return None
    if data[2] not in (0x22, 0x2A):
        return None
    topic_len = data[3]
    if len(data) < 4 + topic_len:
        return None
    try:
        return data[4:4 + topic_len].decode("utf-8")
    except UnicodeDecodeError:
        return None


def extract_product_key(topic: str) -> tuple[str, str] | None:
    """从 topic 路径提取 (product_key, device_id)。

    期望格式：/{product_key}/{device_id}/...
    """
    parts = topic.split("/")
    # parts[0] 是空字符串（因为 topic 以 / 开头）
    if len(parts) >= 3 and parts[0] == "" and len(parts[1]) > 5 and len(parts[2]) > 5:
        # 简单校验：product_key 是字母数字，device_id 通常是 MAC_CAT_SUFFIX 格式
        if re.match(r'^[A-Za-z0-9]{8,12}$', parts[1]):
            return parts[1], parts[2]
    return None


async def send_wake_frames(ws, host: str) -> None:
    """向所有已知 product_key 发送唤醒帧，尝试激活机器人。"""
    print(f"  发送唤醒帧（尝试 {len(KNOWN_PRODUCT_KEYS)} 个 product_key）...")
    # 使用一个占位 device_id，机器人会响应正确的 topic
    placeholder_device = "000000000000_0000_00"
    for pk in KNOWN_PRODUCT_KEYS:
        topic = f"/{pk}/{placeholder_device}/common/notify_app_event"
        try:
            await ws.send(build_raw_frame(topic, b"\x08\x01"))
            await asyncio.sleep(0.05)
        except Exception:
            pass


async def discover(host: str, port: int) -> None:
    url = f"ws://{host}:{port}"
    print(f"正在连接 {url} ...")

    try:
        async with websockets.connect(
            url,
            ping_interval=None,
            ping_timeout=None,
            open_timeout=10,
        ) as ws:
            print(f"连接成功！监听广播帧（最多 60 秒）...\n")

            found_keys: dict[str, str] = {}  # product_key → device_id

            async def listen():
                async for message in ws:
                    if isinstance(message, bytes):
                        topic = parse_topic_from_frame(message)
                        if topic:
                            result = extract_product_key(topic)
                            if result:
                                pk, did = result
                                if pk not in found_keys:
                                    found_keys[pk] = did
                                    print(f"✅ 发现 product_key: {pk}")
                                    print(f"   device_id:   {did}")
                                    print(f"   完整 topic:  {topic}")
                                    print()

            # 先监听 3 秒看是否有自发广播
            try:
                await asyncio.wait_for(listen(), timeout=3.0)
            except asyncio.TimeoutError:
                pass

            if not found_keys:
                print("未收到自发广播，发送唤醒帧...")
                await send_wake_frames(ws, host)
                print("等待机器人响应（30 秒）...\n")
                try:
                    await asyncio.wait_for(listen(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass

            if found_keys:
                print("=" * 50)
                print(f"结论：共发现 {len(found_keys)} 个设备")
                for pk, did in found_keys.items():
                    print(f"  product_key = {pk!r}")
                    print(f"  device_id   = {did!r}")
                print()
                print("下一步：将 product_key 填入")
                print("  custom_components/narwal_cn/const.py → NARWAL_MODELS")
                print("  custom_components/narwal_cn/narwal_client/const.py → KNOWN_PRODUCT_KEYS")
            else:
                print("❌ 未发现任何设备。可能原因：")
                print("  1. 机器人未开机或未在 Wi-Fi 中")
                print("  2. port 9002 被防火墙拦截")
                print("  3. 该型号使用不同协议（非 WebSocket port 9002）")
                print()
                print("建议：用 Wireshark 在手机连接机器人 App 时抓包，")
                print("过滤 ip.addr == " + host + "，查找 WebSocket 升级请求。")

    except ConnectionRefusedError:
        print(f"❌ 连接被拒绝：{url}")
        print("   机器人未开机，或该型号不支持 WebSocket port 9002。")
    except TimeoutError:
        print(f"❌ 连接超时：{url}")
        print("   确认机器人 IP 正确且在同一局域网。")
    except OSError as e:
        print(f"❌ 网络错误：{e}")
    except Exception as e:
        print(f"❌ 意外错误：{type(e).__name__}: {e}")


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    asyncio.run(discover(host, port))


if __name__ == "__main__":
    main()
