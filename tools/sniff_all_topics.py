#!/usr/bin/env python3
"""
sniff_all_topics.py — 抓取机器人所有 WebSocket topic，解码 protobuf 字段。

用途：
  1. 发现耗材/清扫模式/地毯检测等功能的 protobuf 字段编号
  2. 当你在 App 里操作（切换清扫模式、调节出水量等），抓出对应的 topic+payload

用法：
  # 基础模式：被动监听所有广播
  python3 tools/sniff_all_topics.py 10.20.20.120 BYWBPqSxeC

  # 订阅模式：先发 active_robot_publish 再监听（更多 topic）
  python3 tools/sniff_all_topics.py 10.20.20.120 BYWBPqSxeC --subscribe

  # 保存到文件
  python3 tools/sniff_all_topics.py 10.20.20.120 BYWBPqSxeC --out dump.json

依赖：pip3 install websockets bbpb
"""
import asyncio
import json
import struct
import sys
import time
import argparse

try:
    import websockets
    import blackboxprotobuf as bbpb
except ImportError:
    print("缺少依赖：pip3 install websockets bbpb")
    sys.exit(1)

DEFAULT_HOST = "10.20.20.120"
DEFAULT_KEY = "BYWBPqSxeC"
DEFAULT_PORT = 9002


def parse_topic(data: bytes):
    if len(data) < 4 or data[0] != 0x01 or data[2] not in (0x22, 0x2A):
        return None, None
    tlen = data[3]
    if len(data) < 4 + tlen:
        return None, None
    try:
        return data[4:4 + tlen].decode("utf-8"), data[4 + tlen:]
    except UnicodeDecodeError:
        return None, None


def build_frame(topic: str, payload: bytes = b"") -> bytes:
    tb = topic.encode("utf-8")
    return bytes([0x01, len(tb) + 2, 0x22, len(tb)]) + tb + payload


def to_float32(v):
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        try:
            return struct.unpack("f", struct.pack("I", v & 0xFFFFFFFF))[0]
        except Exception:
            pass
    return None


def fmt_value(v, indent=0):
    pad = "  " * indent
    if isinstance(v, dict):
        lines = []
        for k in sorted(v.keys(), key=lambda x: int(x) if str(x).isdigit() else 9999):
            sub = fmt_value(v[k], indent + 1)
            lines.append(f"{pad}  [{k}]: {sub}" if "\n" not in sub else
                         f"{pad}  [{k}]:\n{sub}")
        return "\n".join(lines)
    if isinstance(v, list):
        if len(v) <= 3:
            return f"[{', '.join(str(i) for i in v[:3])}{'...' if len(v)>3 else ''}]"
        return f"list({len(v)} items)"
    if isinstance(v, bytes):
        try:
            text = v.decode("utf-8")
            return f'"{text}"'
        except Exception:
            pass
        return f"bytes({len(v)}) {v[:16].hex()}"
    if isinstance(v, int) and 1_000_000_000 < v < 1_300_000_000:
        f32 = to_float32(v)
        if f32 is not None:
            import math
            if math.isfinite(f32) and -1000 < f32 < 10000:
                return f"{v} (~{f32:.2f} as float32)"
    return str(v)


def print_decoded(short_topic: str, decoded: dict):
    print(f"\n{'='*60}")
    print(f"TOPIC: {short_topic}  [{time.strftime('%H:%M:%S')}]")
    for k in sorted(decoded.keys(), key=lambda x: int(x) if str(x).isdigit() else 9999):
        v = decoded[k]
        fv = fmt_value(v, 0)
        if "\n" in fv:
            print(f"  [{k}]:\n{fv}")
        else:
            print(f"  [{k}]: {fv}")


async def sniff(host: str, product_key: str, port: int, subscribe: bool, outfile: str | None,
                duration: int):
    url = f"ws://{host}:{port}"
    device_id = None
    topic_prefix = f"/{product_key}"
    all_data = {}

    print(f"连接 {url} ...")
    async with websockets.connect(url, ping_interval=None, open_timeout=10) as ws:
        print("已连接！\n")
        print("提示：现在可以在 App 里操作（切换清扫模式、调节出水量、开关地毯检测等），")
        print("      脚本会实时打印收到的 topic 和解码字段。\n")

        # 先被动监听 3 秒，捕获 device_id
        deadline_discover = time.time() + 3
        while time.time() < deadline_discover:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if isinstance(raw, bytes):
                topic, payload = parse_topic(raw)
                if topic:
                    parts = topic.split("/")
                    if len(parts) >= 3 and not device_id:
                        device_id = parts[2]
                        print(f"  发现 device_id: {device_id}")

        if subscribe and device_id:
            # 发送 active_robot_publish 订阅所有 topic
            # payload: {1: duration_seconds(varint), 2: [list of topics]}
            # 简化：发空 payload，让机器人用默认 topic 集广播
            for wake_topic in [
                f"{topic_prefix}/{device_id}/common/notify_app_event",
                f"{topic_prefix}/{device_id}/common/active_robot_publish",
                f"{topic_prefix}/{device_id}/status/app_status_heartbeat",
                f"{topic_prefix}/{device_id}/status/get_device_base_status",
            ]:
                try:
                    await ws.send(build_frame(wake_topic, b"\x08\x01"))
                    await asyncio.sleep(0.1)
                except Exception:
                    pass
            print("  已发送唤醒/订阅帧\n")

        print(f"监听 {duration} 秒，按 Ctrl+C 提前停止...\n")
        deadline = time.time() + duration
        seen_topics = set()

        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                print("\n连接断开")
                break

            if not isinstance(raw, bytes):
                continue

            topic, payload = parse_topic(raw)
            if not topic or payload is None:
                continue

            parts = topic.split("/")
            short = "/".join(parts[3:]) if len(parts) >= 4 else topic

            try:
                decoded, _ = bbpb.decode_message(payload)
            except Exception as e:
                if short not in seen_topics:
                    print(f"\nTOPIC: {short}  (decode failed: {e})")
                    seen_topics.add(short)
                continue

            # 每个 topic 完整打印一次；后续出现时只打印变化的字段
            if short not in all_data:
                all_data[short] = decoded
                print_decoded(short, decoded)
                seen_topics.add(short)
            else:
                # 检测变化
                old = all_data[short]
                changes = {k: v for k, v in decoded.items() if v != old.get(k)}
                if changes:
                    print(f"\n[UPDATE] {short}  [{time.strftime('%H:%M:%S')}]")
                    for k, v in sorted(changes.items(),
                                       key=lambda x: int(x[0]) if str(x[0]).isdigit() else 9999):
                        print(f"  [{k}]: {fmt_value(old.get(k))} → {fmt_value(v)}")
                    all_data[short] = decoded

    print(f"\n\n{'='*60}")
    print(f"共捕获 {len(all_data)} 个不同 topic：")
    for t in sorted(all_data.keys()):
        print(f"  {t}")

    if outfile:
        # 序列化（bytes 转 hex）
        def jsonify(obj):
            if isinstance(obj, bytes):
                return obj.hex()
            if isinstance(obj, dict):
                return {k: jsonify(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [jsonify(i) for i in obj]
            return obj

        with open(outfile, "w") as f:
            json.dump({t: jsonify(d) for t, d in all_data.items()}, f, indent=2,
                      ensure_ascii=False)
        print(f"\n完整数据已保存到 {outfile}")


def main():
    ap = argparse.ArgumentParser(description="Narwal WebSocket topic sniffer")
    ap.add_argument("host", nargs="?", default=DEFAULT_HOST)
    ap.add_argument("product_key", nargs="?", default=DEFAULT_KEY)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--subscribe", action="store_true", help="发送唤醒/订阅帧")
    ap.add_argument("--out", help="保存 JSON 到文件")
    ap.add_argument("--duration", type=int, default=60, help="监听秒数（默认 60）")
    args = ap.parse_args()

    try:
        asyncio.run(sniff(args.host, args.product_key, args.port,
                          args.subscribe, args.out, args.duration))
    except KeyboardInterrupt:
        print("\n用户中断")


if __name__ == "__main__":
    main()
