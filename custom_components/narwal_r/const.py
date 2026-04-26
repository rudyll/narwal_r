"""Constants for the Narwal vacuum integration."""

from homeassistant.const import Platform

from .narwal_client import FanLevel

DOMAIN = "narwal_r"
DEFAULT_PORT = 9002

MANUFACTURER = "云鲸"
MODEL = "逍遥002 Max"

# Model selector for config flow (manual fallback only).
# Keys are user-facing labels; values are product keys.
# Models marked [cloud-only] do NOT support local WebSocket — included for
# completeness but will fail to connect locally.
# Models marked [key needed] have an unknown product_key; contribute yours via
# a GitHub issue after running tools/discover_product_key.py.
NARWAL_MODELS: dict[str, str] = {
    # ── J series ────────────────────────────────────────────────────────────
    "Narwal J4 / J4 Pure": "EHf6cRNRGT",
    "Narwal J4 Lite": "6NjIDYxBXb",
    "Narwal J5": "hEA7OEshlx",
    # J5C / J5X — product_key unknown; run tools/discover_product_key.py and
    # open a GitHub issue to contribute it.

    # ── AX series ───────────────────────────────────────────────────────────
    "Narwal Freo X Slim (AX6)": "tPQJmoIbEC",
    "Narwal Freo X Pro (AX7)": "HgArZ7KuJL",
    "Narwal Freo X (AX8)": "Uuug39n0fD",
    "Narwal Flow (AX12)": "QoEsI5qYXO",
    "Narwal Freo X10 Pro (AX15)": "CNbforyZWI",
    "Narwal Freo X Ultra (AX17)": "E9Q8aDzUbp",
    "Narwal Freo X Ultra (AX18) [cloud-only]": "LnugwMG9ss",
    "Narwal Freo X Ultra (AX19)": "5OMbqk58Sc",
    "Narwal (AX24)": "jI5rHi4mKa",
    "Narwal (AX25)": "UuTSLsMce4",
    "Narwal (AX26)": "qV6BujoYLz",

    # ── BX series ───────────────────────────────────────────────────────────
    "Narwal Freo Y / BX4": "88OLXLpkjT",

    # ── CX series ───────────────────────────────────────────────────────────
    "Narwal Freo Z (CX2)": "7sSZZ4XfTI",
    "Narwal Freo Z10 / CX3 / CX3 Pure": "OlkUn3oUCu",
    "Narwal Freo Z10 Ultra (CX4)": "DrzDKQ0MU8",
    "云鲸逍遥002 Max (CX7)": "BYWBPqSxeC",

    # ── X series ────────────────────────────────────────────────────────────
    "Narwal X30": "mvlduyye85",
    "Narwal X31": "pcbfh2ldvx",

    # ── Fallback ─────────────────────────────────────────────────────────────
    "其他 / 自动检测 (所有已知型号)": "auto",
}

CONF_MODEL = "model"
CONF_PRODUCT_KEY = "product_key"

PLATFORMS: list[Platform] = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SWITCH,
]

FAN_SPEED_MAP: dict[str, FanLevel] = {
    "quiet": FanLevel.QUIET,
    "normal": FanLevel.NORMAL,
    "strong": FanLevel.STRONG,
    "max": FanLevel.MAX,
}

FAN_SPEED_LIST: list[str] = list(FAN_SPEED_MAP.keys())
