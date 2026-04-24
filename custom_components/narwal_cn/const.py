"""Constants for the Narwal vacuum integration."""

from homeassistant.const import Platform

from .narwal_client import FanLevel

DOMAIN = "narwal_cn"
DEFAULT_PORT = 9002

MANUFACTURER = "云鲸"
MODEL = "逍遥002 Max"

# Model selector for config flow.
# Keys are user-facing labels; values are product key prefixes.
# "auto" cycles all known keys during discovery (slower, fallback).
NARWAL_MODELS: dict[str, str] = {
    "云鲸逍遥002 Max": "BYWBPqSxeC",  # confirmed via local WebSocket broadcast 2026-04-24
    "Narwal Flow (AX12)": "QoEsI5qYXO",
    "Narwal Freo Z10 Ultra (CX4)": "DrzDKQ0MU8",
    "Narwal Freo X10 Pro (AX15)": "CNbforyZWI",
    "其他 / 自动检测": "auto",
}

CONF_MODEL = "model"
CONF_PRODUCT_KEY = "product_key"

PLATFORMS: list[Platform] = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
]

FAN_SPEED_MAP: dict[str, FanLevel] = {
    "quiet": FanLevel.QUIET,
    "normal": FanLevel.NORMAL,
    "strong": FanLevel.STRONG,
    "max": FanLevel.MAX,
}

FAN_SPEED_LIST: list[str] = list(FAN_SPEED_MAP.keys())
