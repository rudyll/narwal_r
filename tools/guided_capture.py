#!/usr/bin/env python3
"""
guided_capture.py — 引导式 STATUS 字段发现工具

通过对比操作前后的 STATUS 广播（0x22 帧）字段变化，
确认各 App 功能对应的 protobuf 字段号和值编码。

每步节奏：
  1. 脚本打印：导航路径 + 操作说明
  2. 你在 App 里导航到目标页面
  3. 按 Enter 开始监听
  4. 在 App 里切换功能
  5. 完成后按 Enter 结束
  6. 脚本显示变化的字段

按键：
  Enter         → 确认（就位 / 操作完成）
  s + Enter     → 跳过当前步骤
  q + Enter     → 退出

用法：
  python3 tools/guided_capture.py <robot_ip> <product_key>
  python3 tools/guided_capture.py <robot_ip> <product_key> --out results.json
  python3 tools/guided_capture.py <robot_ip> <product_key> --start 6   # 1-based
  python3 tools/guided_capture.py --list                                # 显示任务列表

依赖：pip3 install websockets bbpb
"""
import asyncio
import json
import math
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

DEFAULT_PORT = 9002

# ─── 任务列表 ──────────────────────────────────────────────────────────────────
# (task_id, 显示名称, App 导航路径, 操作说明)
# nav 为空 → 继承上一步导航
TASKS = [
    # ── 清洁模式 ───────────────────────────────────────────────────────────────
    ("clean_mode_ai",         "清洁模式 → Ai 鲸灵托管", "主页 → 底部清洁模式卡片 → 向左滑动", "点选「Ai 鲸灵托管」"),
    ("clean_mode_sweep_mop",  "清洁模式 → 扫拖同时",    "",                                   "点选「扫拖同时」"),
    ("clean_mode_sweep_then", "清洁模式 → 先扫后拖",    "",                                   "点选「先扫后拖」"),
    ("clean_mode_sweep",      "清洁模式 → 扫地",        "",                                   "点选「扫地」"),
    ("clean_mode_mop",        "清洁模式 → 拖地",        "",                                   "点选「拖地」"),

    # ── 扫地吸力 ───────────────────────────────────────────────────────────────
    ("suction_quiet",    "扫地吸力 → 静音",  "设置 → 鲸灵托管 → 扫地吸力",  "选「静音」"),
    ("suction_standard", "扫地吸力 → 标准",  "",                             "选「标准」（若存在）"),
    ("suction_strong",   "扫地吸力 → 强力",  "",                             "选「强力」"),
    ("suction_max",      "扫地吸力 → MAX",   "",                             "选「MAX」（若存在）"),

    # ── 拖地湿度 ───────────────────────────────────────────────────────────────
    ("mop_dry",      "拖地湿度 → 最低(干拖)", "设置 → 鲸灵托管 → 拖地湿度",  "选最低档"),
    ("mop_standard", "拖地湿度 → 标准",       "",                             "选「标准」"),
    ("mop_wet",      "拖地湿度 → 最高(湿拖)", "",                             "选最高档"),

    # ── 清洁页开关 ─────────────────────────────────────────────────────────────
    ("carpet_priority_on",  "优先清洁地毯 → 开",  "设置 → 清洁 → 优先清洁地毯",  "开启"),
    ("carpet_priority_off", "优先清洁地毯 → 关",  "",                             "关闭（还原）"),
    ("carpet_deep_on",      "地毯深度清洁 → 开",  "设置 → 清洁 → 地毯深度清洁",  "开启"),
    ("carpet_deep_off",     "地毯深度清洁 → 关",  "",                             "关闭（还原）"),
    ("deep_corner_on",      "深度边角清洁 → 开",  "设置 → 清洁 → 深度边角清洁",  "开启"),
    ("deep_corner_off",     "深度边角清洁 → 关",  "",                             "关闭（还原）"),

    # ── AI 识别 ────────────────────────────────────────────────────────────────
    ("obstacle_smart", "避障策略 → 智能",  "设置 → AI识别 → 避障策略",  "选「智能」"),
    ("obstacle_safe",  "避障策略 → 安全",  "",                          "选「安全」"),

    # ── 通用开关 ───────────────────────────────────────────────────────────────
    ("child_lock_on",      "童锁 → 开",       "设置 → 通用 → 童锁",       "开启"),
    ("child_lock_off",     "童锁 → 关",       "",                         "关闭（还原）"),
    ("dnd_on",             "勿扰模式 → 开",   "设置 → 通用 → 勿扰模式",   "开启"),
    ("dnd_off",            "勿扰模式 → 关",   "",                         "关闭（还原）"),
    ("altitude_on",        "高原模式 → 开",   "设置 → 通用 → 高原模式",   "开启"),
    ("altitude_off",       "高原模式 → 关",   "",                         "关闭（还原）"),
    ("auto_power_off_on",  "自动关机 → 开",   "设置 → 通用 → 自动关机",   "开启"),
    ("auto_power_off_off", "自动关机 → 关",   "",                         "关闭（还原）"),

    # ── 基站开关 ───────────────────────────────────────────────────────────────
    ("hot_water_on",       "智控热水洗拖布 → 开",  "设置 → 基站 → 智控热水洗拖布",    "开启"),
    ("hot_water_off",      "智控热水洗拖布 → 关",  "",                                "关闭（还原）"),
    ("auto_detergent_on",  "自动添加清洁剂 → 开",  "设置 → 基站 → 自动添加清洁剂",    "开启"),
    ("auto_detergent_off", "自动添加清洁剂 → 关",  "",                                "关闭（还原）"),
    ("antibacterial_on",   "自动抑菌尘盒 → 开",    "设置 → 基站 → 自动抑菌尘盒/尘袋", "开启"),
    ("antibacterial_off",  "自动抑菌尘盒 → 关",    "",                                "关闭（还原）"),
    ("auto_dust_on",       "自动集尘 → 开",        "设置 → 基站 → 自动集尘",          "开启"),
    ("auto_dust_off",      "自动集尘 → 关",        "",                                "关闭（还原）"),

    # ── 基站选项 ───────────────────────────────────────────────────────────────
    ("dry_quiet",  "拖布烘干强度 → 静音",  "设置 → 基站 → 拖布烘干强度",  "选「静音烘干」"),
    ("dry_strong", "拖布烘干强度 → 强力",  "",                            "选「强力烘干」"),
    ("dry_smart",  "拖布烘干强度 → 智能",  "",                            "选「智能烘干」（还原）"),
    ("dust_quiet",  "集尘档位 → 静音",     "设置 → 基站 → 集尘档位",      "选「静音集尘」"),
    ("dust_strong", "集尘档位 → 强劲",     "",                            "选「强劲集尘」（还原）"),
    ("auto_dust_freq_every", "自动集尘频率 → 每次", "设置 → 基站 → 自动集尘 → 频率", "选「每次执行」"),
    ("auto_dust_freq_smart", "自动集尘频率 → 智能", "",                              "选「智能执行」（还原）"),

    # ── 有宠家庭 ───────────────────────────────────────────────────────────────
    ("pet_dirt_on",   "AI 污渍检测 → 开",    "设置 → 有宠家庭",  "开启 AI 污渍检测"),
    ("pet_dirt_off",  "AI 污渍检测 → 关",    "",                 "关闭（还原）"),
    ("pet_waste_on",  "AI 排泄物检测 → 开",  "设置 → 有宠家庭",  "开启 AI 排泄物检测"),
    ("pet_waste_off", "AI 排泄物检测 → 关",  "",                 "关闭（还原）"),

    # ── 耗材字段发现（不需要操作 App）─────────────────────────────────────────
    # 已知当前剩余值：集尘袋/尘盒/滤网=90h, 滚刷/边刷/拖布=150h, 传感器=80h, 基站滤网=30h
    ("consumables_dump", "耗材字段发现（不操作 App，直接按 Enter）",
     "无需导航",
     "不要在 App 操作，脚本自动在 STATUS 里搜索值为 30/80/90/150 的字段"),
]


# ─── 工具函数 ──────────────────────────────────────────────────────────────────

def parse_frame(data: bytes):
    if len(data) < 4 or data[0] != 0x01 or data[2] not in (0x22, 0x2A):
        return None, None, None
    ft = data[2]
    tlen = data[3]
    if len(data) < 4 + tlen:
        return None, None, None
    try:
        return data[4:4 + tlen].decode("utf-8"), data[4 + tlen:], ft
    except UnicodeDecodeError:
        return None, None, None


def decode_pb(payload: bytes):
    try:
        msg, _ = bbpb.decode_message(payload)
        return msg
    except Exception:
        return None


def build_frame(topic: str, payload: bytes = b"") -> bytes:
    tb = topic.encode("utf-8")
    return bytes([0x01, len(tb) + 2, 0x22, len(tb)]) + tb + payload


async def request_status(ws, product_key: str, device_id: str):
    """发送状态请求帧，触发机器人广播当前状态。"""
    if not device_id:
        return
    prefix = f"/{product_key}/{device_id}"
    for topic in [
        f"{prefix}/status/get_device_base_status",
        f"{prefix}/common/active_robot_publish",
        f"{prefix}/status/app_status_heartbeat",
    ]:
        try:
            await ws.send(build_frame(topic, b"\x08\x01"))
            await asyncio.sleep(0.05)
        except Exception:
            pass


def to_float32(v):
    if isinstance(v, int):
        try:
            f = struct.unpack("f", struct.pack("I", v & 0xFFFFFFFF))[0]
            if math.isfinite(f) and -1000 < f < 10000:
                return f
        except Exception:
            pass
    return None


def fmt_val(v):
    if isinstance(v, dict):
        inner = ", ".join(
            f"[{k}]={fmt_val(vv)}"
            for k, vv in sorted(v.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 9999)
        )
        return "{" + inner + "}"
    if isinstance(v, list):
        return f"[…×{len(v)}]" if len(v) > 3 else str(v)
    if isinstance(v, bytes):
        try:
            return f'"{v.decode()}"'
        except Exception:
            return f"0x{v[:8].hex()}"
    if isinstance(v, int):
        f32 = to_float32(v)
        if f32 is not None:
            return f"{v}(≈{f32:.2f})"
    return str(v)


def flatten_simple(msg: dict, prefix="") -> dict[str, int | str]:
    """Flatten protobuf dict to {field_path: value} keeping only int/str leaves."""
    result = {}
    for k, v in msg.items():
        path = f"{prefix}[{k}]"
        if isinstance(v, (int, str, float)):
            result[path] = v
        elif isinstance(v, bytes):
            result[path] = v.hex()
        elif isinstance(v, dict):
            result.update(flatten_simple(v, path))
    return result


# ─── 异步核心 ──────────────────────────────────────────────────────────────────

async def reader_loop(ws, queue: asyncio.Queue):
    try:
        while True:
            raw = await ws.recv()
            if isinstance(raw, bytes):
                topic, payload, ft = parse_frame(raw)
                if topic:
                    await queue.put((time.time(), topic, payload, ft))
    except Exception:
        pass


async def collect_status(queue: asyncio.Queue, seconds: float) -> dict[str, dict]:
    """Collect STATUS (0x22) frames for `seconds`, return latest snapshot per topic."""
    snapshot: dict[str, dict] = {}
    deadline = time.time() + seconds
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            ts, topic, payload, ft = await asyncio.wait_for(queue.get(), timeout=min(remaining, 0.3))
            if ft == 0x22:
                msg = decode_pb(payload)
                if msg:
                    parts = topic.split("/")
                    short = "/".join(parts[3:]) if len(parts) >= 4 else topic
                    snapshot[short] = msg
        except asyncio.TimeoutError:
            pass
    return snapshot


def diff_snapshots(before: dict[str, dict], after: dict[str, dict]) -> list[tuple]:
    """Return list of (topic_short, field, old_value, new_value) for changed fields."""
    changes = []
    for short in set(before) | set(after):
        old_flat = flatten_simple(before.get(short, {}))
        new_flat = flatten_simple(after.get(short, {}))
        all_keys = set(old_flat) | set(new_flat)
        for key in sorted(all_keys, key=lambda x: [int(p.strip("[]")) if p.strip("[]").isdigit() else p
                                                    for p in x.split("][")]):
            ov = old_flat.get(key)
            nv = new_flat.get(key)
            if ov != nv:
                changes.append((short, key, ov, nv))
    return changes


# ─── 主流程 ────────────────────────────────────────────────────────────────────

async def run(host, product_key, port, outfile, start_idx, list_only):
    last_nav = ""
    if list_only:
        print(f"{'─'*60}")
        for i, (tid, name, nav, instr) in enumerate(TASKS):
            nav = nav or last_nav
            last_nav = nav
            print(f"  {i+1:2d}. {name}")
        print(f"{'─'*60}")
        print(f"  共 {len(TASKS)} 项")
        return

    results = {}
    if outfile:
        try:
            with open(outfile) as f:
                results = json.load(f)
            print(f"  已加载已有结果：{len(results)} 项（已捕获步骤将自动跳过）")
        except Exception:
            pass

    url = f"ws://{host}:{port}"
    print(f"\n连接 {url} ...")
    async with websockets.connect(url, ping_interval=None, open_timeout=10) as ws:
        print("已连接！\n")

        # 发现 device_id
        device_id = None
        print("  等待广播（最多 10 秒）...")
        for _ in range(30):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.4)
            except asyncio.TimeoutError:
                continue
            if isinstance(raw, bytes):
                topic, _, _ = parse_frame(raw)
                if topic:
                    parts = topic.split("/")
                    if len(parts) >= 3:
                        device_id = parts[2]
                        print(f"  device_id: {device_id}\n")
                        break

        queue: asyncio.Queue = asyncio.Queue()
        asyncio.create_task(reader_loop(ws, queue))
        loop = asyncio.get_event_loop()

        # ── 建立初始基准快照 ──────────────────────────────────────────────────
        print("  请求状态并建立基准快照...")
        await request_status(ws, product_key, device_id)
        baseline = await collect_status(queue, 5.0)
        if not baseline:
            await request_status(ws, product_key, device_id)
            baseline = await collect_status(queue, 5.0)
        total_fields = sum(len(flatten_simple(v)) for v in baseline.values())
        print(f"  基准快照：{len(baseline)} 个 topic，{total_fields} 个字段\n")

        total = len(TASKS)
        last_nav = ""

        for i, (task_id, name, nav, instruction) in enumerate(TASKS):
            idx = i + 1
            if idx < start_idx:
                continue
            nav = nav or last_nav
            if nav:
                last_nav = nav

            if task_id in results:
                print(f"[{idx}/{total}] {name}  ✓ 已捕获，跳过")
                continue

            print(f"\n{'=' * 62}")
            print(f"  [{idx}/{total}]  {name}")
            if nav:
                print(f"  导航：{nav}")
            print(f"  操作：{instruction}")
            print()

            while True:
                # ── 耗材特殊任务 ──────────────────────────────────────────────
                if task_id == "consumables_dump":
                    resp = await loop.run_in_executor(
                        None, input, "  按 Enter 搜索耗材字段（s=跳过）... "
                    )
                    if resp.strip().lower() == "s":
                        print("  跳过")
                        break
                    CONSUMABLE_VALUES = {30, 80, 90, 150}
                    snap = await collect_status(queue, 5.0)
                    snap = {**baseline, **snap}
                    hits: dict[str, dict] = {}
                    for short, msg in snap.items():
                        flat = flatten_simple(msg)
                        matched = {k: v for k, v in flat.items()
                                   if isinstance(v, int) and v in CONSUMABLE_VALUES}
                        if matched:
                            hits[short] = matched
                    if hits:
                        print(f"\n  ★ 发现可能的耗材字段：")
                        for short, fields in hits.items():
                            print(f"  {short}:")
                            for k, v in fields.items():
                                print(f"    {k} = {v}h")
                        action = await loop.run_in_executor(None, input, "\n  y=保存  s=跳过 → ")
                        if action.strip().lower() == "y":
                            results[task_id] = {"name": name, "consumable_fields": hits}
                            _save(results, outfile)
                            print("  ✅ 已保存")
                    else:
                        print("  （未找到匹配值，可能字段存储方式不同）")
                    break

                # ── 普通任务：Step 1 — 就位 ───────────────────────────────────
                resp = await loop.run_in_executor(
                    None, input, "  导航完成后按 Enter（s=跳过 / q=退出）... "
                )
                resp = resp.strip().lower()
                if resp == "q":
                    print("\n已退出。")
                    return
                if resp == "s":
                    print(f"  跳过")
                    break

                # 刷新基准：主动请求一次，确保有最新状态
                await request_status(ws, product_key, device_id)
                fresh = await collect_status(queue, 3.0)
                baseline.update(fresh)
                print(f"  基准已刷新（{len(flatten_simple(baseline.get('status/robot_base_status', {})))} 个字段）")

                # ── Step 2 — 操作窗口 ─────────────────────────────────────────
                print(f"  ▶ 现在在 App 里操作，完成后按 Enter...")
                # 持续收帧直到用户按 Enter
                during_frames: list = []

                async def collect_until_enter():
                    """Collect STATUS frames while waiting for Enter."""
                    nonlocal during_frames
                    while True:
                        try:
                            item = await asyncio.wait_for(queue.get(), timeout=0.2)
                            during_frames.append(item)
                        except asyncio.TimeoutError:
                            pass

                collector = asyncio.create_task(collect_until_enter())
                await loop.run_in_executor(None, input, "")
                collector.cancel()

                # 主动请求状态，触发机器人广播最新值
                await request_status(ws, product_key, device_id)
                tail = await collect_status(queue, 3.0)

                # ── 构建操作后快照 ────────────────────────────────────────────
                after_snap = dict(baseline)
                for ts, topic, payload, ft in during_frames:
                    if ft == 0x22:
                        msg = decode_pb(payload)
                        if msg:
                            parts = topic.split("/")
                            short = "/".join(parts[3:]) if len(parts) >= 4 else topic
                            after_snap[short] = msg
                after_snap.update(tail)

                # ── 显示变化 ──────────────────────────────────────────────────
                changes = diff_snapshots(baseline, after_snap)
                # 过滤噪音字段（时间戳、位置等）
                NOISE_KEYS = {"[2]", "[1]", "[3]", "[7]", "[10]", "[11]", "[12]"}
                NOISE_TOPICS = {"map/display_map", "status/working_status",
                                "status/point_navi_plan_traj"}
                filtered = [(t, k, ov, nv) for t, k, ov, nv in changes
                            if t not in NOISE_TOPICS and k not in NOISE_KEYS]

                print()
                if filtered:
                    print(f"  ★ 检测到 {len(filtered)} 个字段变化：")
                    for t, k, ov, nv in filtered:
                        ov_s = fmt_val(ov) if ov is not None else "（无）"
                        nv_s = fmt_val(nv) if nv is not None else "（无）"
                        print(f"    {t}  {k}:  {ov_s}  →  {nv_s}")
                else:
                    all_changes = diff_snapshots(baseline, after_snap)
                    if all_changes:
                        print(f"  （仅检测到噪音字段变化，共 {len(all_changes)} 个，可能是位置/时间戳）")
                    else:
                        print("  （未检测到任何字段变化）")

                action = await loop.run_in_executor(
                    None, input, "\n  y=保存  r=重试  s=跳过 → "
                )
                action = action.strip().lower()

                if action == "y":
                    results[task_id] = {
                        "name": name,
                        "changes": [
                            {"topic": t, "field": k,
                             "before": str(ov) if ov is not None else None,
                             "after": str(nv) if nv is not None else None}
                            for t, k, ov, nv in filtered
                        ] or [
                            {"topic": t, "field": k,
                             "before": str(ov) if ov is not None else None,
                             "after": str(nv) if nv is not None else None}
                            for t, k, ov, nv in changes
                        ],
                    }
                    _save(results, outfile)
                    baseline.update(after_snap)
                    print(f"  ✅ 已保存 ({task_id})")
                    break
                elif action == "s":
                    print(f"  跳过 {task_id}")
                    baseline.update(after_snap)
                    break
                else:
                    print("  重试...")
                    baseline.update(after_snap)

    print(f"\n\n{'=' * 62}")
    print(f"  共捕获 {len(results)} 项")
    if outfile and results:
        print(f"  结果已保存到 {outfile}")


def _save(results, outfile):
    if outfile:
        with open(outfile, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description="Narwal 引导式字段发现工具")
    ap.add_argument("host", nargs="?", default="")
    ap.add_argument("product_key", nargs="?", default="")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--out", default="capture_results.json",
                    help="结果文件（默认 capture_results.json）")
    ap.add_argument("--start", type=int, default=1, metavar="N",
                    help="从第 N 项开始（1-based）")
    ap.add_argument("--list", action="store_true", help="只显示任务列表")
    args = ap.parse_args()

    if not args.host and not args.list:
        ap.print_help()
        sys.exit(1)

    try:
        asyncio.run(run(args.host, args.product_key, args.port,
                        args.out, args.start, args.list))
    except KeyboardInterrupt:
        print("\n中断")


if __name__ == "__main__":
    main()
