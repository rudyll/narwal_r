"""Config flow for Narwal CN vacuum integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .narwal_client import NarwalClient, NarwalCommandError, NarwalConnectionError
from .const import CONF_MODEL, CONF_PRODUCT_KEY, DEFAULT_PORT, DOMAIN, NARWAL_MODELS

_LOGGER = logging.getLogger(__name__)

MODEL_OPTIONS = list(NARWAL_MODELS.keys())

# Step 1: user only needs to enter IP (and optionally port).
# product_key is auto-detected via passive WebSocket listen.
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Optional("port", default=DEFAULT_PORT): int,
    }
)

# Step 2: shown only when auto-detection fails — lets user manually pick a model.
STEP_MANUAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODEL, default=MODEL_OPTIONS[0]): vol.In(MODEL_OPTIONS),
    }
)


class NarwalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow: IP → auto-detect product_key → create entry.

    Auto-detection works by opening a raw WebSocket to port 9002 and
    listening passively for any broadcast frame.  The robot embeds its
    product_key in every topic path (/{product_key}/{device_id}/…), so
    the first frame that arrives is enough to identify the model.

    If no frame arrives within the passive window, the client falls back
    to the existing wake-frame cycle (tries all KNOWN_PRODUCT_KEYS).

    If that also fails the user is offered a manual model selector as a
    last resort.
    """

    VERSION = 2

    def __init__(self) -> None:
        self._host: str = ""
        self._port: int = DEFAULT_PORT
        self._product_key: str = ""
        self._device_id: str = ""
        self._firmware: str = ""

    # ------------------------------------------------------------------
    # Step 1: enter IP
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """User enters IP address (model is auto-detected)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input["host"]
            self._port = user_input.get("port", DEFAULT_PORT)

            # Try auto-detection first (passive listen, then wake cycle).
            result = await self._try_connect(product_key=None)
            if result == "ok":
                return self._create_entry()
            if result == "already_configured":
                return self.async_abort(reason="already_configured")
            if result == "no_key":
                # Auto-detection could not find the product_key — ask user.
                return await self.async_step_manual()
            # result == "cannot_connect"
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2 (fallback): manual model picker
    # ------------------------------------------------------------------

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fallback step: user manually selects a model."""
        errors: dict[str, str] = {}

        if user_input is not None:
            model_label = user_input[CONF_MODEL]
            pk = NARWAL_MODELS[model_label]
            result = await self._try_connect(product_key=None if pk == "auto" else pk)
            if result == "ok":
                return self._create_entry()
            if result == "already_configured":
                return self.async_abort(reason="already_configured")
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="manual",
            data_schema=STEP_MANUAL_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"host": self._host},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _try_connect(self, product_key: str | None) -> str:
        """Attempt connection and device discovery.

        Returns:
            "ok"                 — success, self._product_key / _device_id set
            "cannot_connect"     — WebSocket refused / timeout
            "already_configured" — device already in HA
            "no_key"             — connected but could not determine product_key
        """
        topic_prefix = None if product_key is None else f"/{product_key}"
        client = NarwalClient(host=self._host, port=self._port, topic_prefix=topic_prefix)
        try:
            await client.connect()

            # Phase A: passive listen (5 s) — robot broadcasts include product_key.
            # Works even without knowing the key in advance.
            if product_key is None:
                discovered = await _passive_detect_product_key(client, timeout=5.0)
                if discovered:
                    client.topic_prefix = f"/{discovered}"

            # Phase B: active wake + device_id discovery.
            await client.discover_device_id(timeout=20.0)
            await client.drain_ws_buffer()
            device_info = await client.get_device_info()

        except (NarwalConnectionError, NarwalCommandError, OSError, TimeoutError) as ex:
            _LOGGER.debug("Connection attempt failed: %s: %s", type(ex).__name__, ex)
            return "cannot_connect"
        except Exception as ex:
            _LOGGER.warning("Unexpected error during setup: %s: %s", type(ex).__name__, ex)
            return "cannot_connect"
        else:
            resolved_key = client.topic_prefix.lstrip("/") if client.topic_prefix else ""
            if not resolved_key:
                return "no_key"

            self._product_key = resolved_key
            self._device_id = device_info.device_id
            self._firmware = device_info.firmware_version

            try:
                await self.async_set_unique_id(self._device_id)
                self._abort_if_unique_id_configured()
            except Exception:
                return "already_configured"

            return "ok"
        finally:
            await client.disconnect()

    def _create_entry(self) -> ConfigFlowResult:
        """Build the config entry title and data dict."""
        # Find a human-readable model label for the resolved product key.
        label = next(
            (name for name, pk in NARWAL_MODELS.items() if pk == self._product_key),
            f"Narwal {self._product_key}",
        )
        return self.async_create_entry(
            title=label,
            data={
                "host": self._host,
                "port": self._port,
                "device_id": self._device_id,
                CONF_PRODUCT_KEY: self._product_key,
                CONF_MODEL: label,
            },
        )


# ------------------------------------------------------------------
# Passive product_key detection (no prior key needed)
# ------------------------------------------------------------------

async def _passive_detect_product_key(
    client: NarwalClient, timeout: float = 5.0
) -> str | None:
    """Listen for one broadcast frame and extract the product_key from its topic.

    The robot embeds the product_key in every outgoing topic:
      /{product_key}/{device_id}/category/command

    Returns the detected product_key, or None if no frame arrived.
    """
    import asyncio
    from .narwal_client.protocol import parse_frame, ProtocolError

    ws = getattr(client, "_ws", None)
    if ws is None:
        return None

    deadline = asyncio.get_event_loop().time() + timeout
    try:
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 1.0))
            except asyncio.TimeoutError:
                continue

            if not isinstance(raw, bytes):
                continue
            try:
                msg = parse_frame(raw)
            except ProtocolError:
                continue

            parts = msg.topic.split("/")
            # topic = /{product_key}/{device_id}/...  →  parts[1] is the key
            if len(parts) >= 3 and parts[0] == "" and len(parts[1]) >= 8:
                _LOGGER.debug("Passive detection found product_key=%s", parts[1])
                return parts[1]
    except Exception as ex:
        _LOGGER.debug("Passive detection error: %s", ex)

    return None
