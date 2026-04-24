#!/usr/bin/env python3
"""
probe_robot.py — 验证机器人 WebSocket 连接，获取基础状态。

用法：
    python3 tools/probe_robot.py [IP] [PRODUCT_KEY] [PORT]
    python3 tools/probe_robot.py 10.10.10.220
    python3 tools/probe_robot.py 10.10.10.220 QoEsI5qYXO

不提供 PRODUCT_KEY 时使用自动检测模式（较慢，尝试所有已知 key）。

依赖（在 tools/ 目录下运行）：
    pip3 install bbpb websockets Pillow
"""

import asyncio
import struct
import sys
import os

# 将 custom_components/narwal_cn 加入 Python 路径
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "custom_components", "narwal_cn"))

try:
    from narwal_client import NarwalClient, NarwalConnectionError, WorkingStatus
    from narwal_client.models import NarwalState
except ImportError as e:
    print(f"导入失败：{e}")
    print("请确认已安装依赖：pip3 install bbpb websockets Pillow")
    sys.exit(1)

DEFAULT_HOST = "10.10.10.220"
DEFAULT_PORT = 9002


def fmt_battery(raw: int) -> str:
    """将 float32 整数位转换为百分比字符串。"""
    try:
        val = struct.unpack("f", struct.pack("I", raw))[0]
        return f"{val:.1f}%"
    except Exception:
        return f"raw={raw}"


def fmt_status(ws: WorkingStatus | int) -> str:
    try:
        return WorkingStatus(ws).name
    except ValueError:
        return f"未知状态({ws})"


async def probe(host: str, product_key: str | None, port: int) -> None:
    topic_prefix = None if product_key is None else f"/{product_key}"
    mode = "自动检测" if product_key is None else f"指定 key={product_key}"
    print(f"目标：ws://{host}:{port}  模式：{mode}")
    print("连接中...\n")

    client = NarwalClient(host=host, port=port, topic_prefix=topic_prefix)

    try:
        await client.connect()
        print("✅ WebSocket 连接成功")

        print("发现 device_id（唤醒机器人，最多 20 秒）...")
        await client.discover_device_id(timeout=20.0)
        print(f"✅ 发现 device_id，topic_prefix = {client.topic_prefix!r}")

        await client.drain_ws_buffer()

        print("\n获取设备信息...")
        info = await client.get_device_info()
        print(f"  device_id:       {info.device_id}")
        print(f"  product_key:     {client.topic_prefix.lstrip('/')}")
        print(f"  firmware:        {info.firmware_version or '(未知)'}")

        print("\n等待状态广播（最多 15 秒）...")
        state: NarwalState = client.state

        # 等待收到 robot_base_status 广播
        for _ in range(30):
            await asyncio.sleep(0.5)
            if client.state.battery_level is not None:
                state = client.state
                break

        print("\n=== 机器人状态 ===")
        if state.battery_level is not None:
            print(f"  电量：          {fmt_battery(state.battery_level)}")
        else:
            print("  电量：          (未收到广播)")
        print(f"  工作状态：      {fmt_status(state.working_status)}")
        print(f"  停靠中：        {'是' if state.is_docked else '否'}")
        if state.cleaning_area is not None:
            print(f"  累计清扫面积：  {state.cleaning_area / 10000:.2f} m²")
        if state.cleaning_time is not None:
            print(f"  累计清扫时间：  {state.cleaning_time} 秒")

        print("\n=== 结论 ===")
        pk = client.topic_prefix.lstrip("/")
        print(f"✅ 机器人响应正常，使用 product_key = {pk!r}")
        print()
        print("下一步：将以下内容更新到集成配置：")
        print(f'  custom_components/narwal_cn/const.py → NARWAL_MODELS["云鲸逍遥002 Max"] = "{pk}"')
        print(f'  custom_components/narwal_cn/narwal_client/const.py → 在 KNOWN_PRODUCT_KEYS 首位添加 "{pk}"')

    except NarwalConnectionError as e:
        print(f"\n❌ 连接失败：{e}")
        print("   检查：1) 机器人已开机  2) IP 正确  3) 同一局域网  4) port 9002 未被防火墙拦截")
    except asyncio.TimeoutError:
        print(f"\n❌ 超时：机器人未在规定时间内响应")
        print("   尝试：先打开云鲸 App 唤醒机器人，再运行此脚本")
    except Exception as e:
        print(f"\n❌ 错误：{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()


def main() -> None:
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    product_key = sys.argv[2] if len(sys.argv) > 2 else None
    port = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_PORT
    asyncio.run(probe(host, product_key, port))


if __name__ == "__main__":
    main()
