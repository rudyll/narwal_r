# Narwal Robot Vacuum — Home Assistant Integration

A fully **local, cloud-independent** [Home Assistant](https://www.home-assistant.io/) custom integration for Narwal robot vacuums. Communicates directly with your vacuum over your local network via WebSocket — no cloud account or internet connection required.

> **v1.0.0** — Vacuum control, sensors, live map with room labels, obstacle overlay, and room-specific cleaning. Available via HACS.

## Device Compatibility

This integration uses a **local WebSocket connection on port 9002**. Only models that expose this port are supported.

| Model | Status | Notes |
|-------|--------|-------|
| **Narwal Flow** (AX12) | **Working** | Primary development target |
| **Freo Z10 Ultra** (CX4) | **Working** | Community confirmed |
| **Freo X10 Pro** (AX15) | **Working** | Community confirmed ([#12](https://github.com/sjmotew/NarwalIntegration/issues/12)) |
| **Freo Z Ultra** (CX7) | **Not Compatible** | Port 9002 open but no local broadcasts; cloud-only ([#5](https://github.com/sjmotew/NarwalIntegration/issues/5), confirmed by @Folg0re) |
| **Freo X Ultra** (AX18/AX19) | **Not Compatible** | Uses ZeroMQ (port 6789) + Tuya cloud, not WebSocket ([#4](https://github.com/sjmotew/NarwalIntegration/issues/4)) |
| **Freo X Plus** | **Not Compatible** | Cloud-only — no local API |
| **Narwal J-series** (J1/J4/J5) | **Not Compatible** | J1: HTTP-only (port 8080); J4/J5: cloud-only (Tuya) |

Models marked **Not Compatible** use a different protocol or are cloud-only. This is a hardware/firmware limitation.

**Other models?** Check with `nmap -p 9002 <your-vacuum-ip>`. If open, [open an issue](https://github.com/sjmotew/NarwalIntegration/issues/new/choose) with your model and results.

## Features

### Vacuum Control
- **Start / Stop / Pause / Resume** — all commands validated on hardware
- **Room-specific cleaning** — select rooms from the HA UI (requires HA 2026.3+)
- **Return to dock** / **Locate** (robot announces "Robot is here")
- **Fan speed** — Quiet, Normal, Strong, Max (set-only; robot doesn't broadcast current level)

### Sensors
- Battery level, cleaning area, cleaning time, firmware version
- Docked status (binary sensor), charging state (Charging / Fully Charged / Not Charging)

### Live Map
- Color-coded floor plan with room labels (all rooms — user-named and auto-generated)
- Furniture/obstacle overlay from the robot's stored map data
- Dock marker and live robot trail during cleaning (~1.5s refresh)

### Connectivity
- Real-time WebSocket push updates
- Auto-reconnect with exponential backoff
- Wake system for sleeping robots + keepalive heartbeat
- 60-second polling fallback

## Installation

### HACS (Recommended)

1. Open **HACS** > three-dot menu > **Custom repositories**
2. Add: `https://github.com/sjmotew/NarwalIntegration` (category: Integration)
3. Find **Narwal Flow Robot Vacuum** and click **Download**
4. **Restart Home Assistant**

### Manual

1. Copy `custom_components/narwal/` to your HA `config/custom_components/` directory
2. **Restart Home Assistant**

### Setup

1. **Settings > Devices & Services > Add Integration** > search "Narwal"
2. Enter your vacuum's IP address and select your model
3. Entities are created automatically

> **Tip:** Assign a static IP to your vacuum in your router.

## Requirements

- Narwal vacuum on the same local network as Home Assistant
- Port 9002 reachable (no firewall blocking)
- Home Assistant 2025.1.0+ / Python 3.12+

## Known Limitations

- **Wake from deep sleep is unreliable** — robot may not respond after long idle periods. Opening the Narwal app briefly can help.
- **Single connection** — close the Narwal app before using HA to avoid conflicts.
- **Fan speed is set-only** — robot doesn't broadcast its current level.
- **Default clean settings** — start and room-specific clean use max suction, wet mop, single pass. Per-room customization is not yet available.
- **Map may be stale** — robot can return an old map. A new clean cycle typically refreshes it.

## Future Features (On Hold)

These features have been researched and probed but are **on hold** pending further reverse engineering:

| Feature | Status | Blocker |
|---------|--------|---------|
| **Camera snapshots** | Client method works (robot returns ~170KB) | Image data is **AES-encrypted** — APK reverse engineering needed for decryption key |
| **Camera LED control** | Partial response from robot | Correct payload format unconfirmed; needs idle-state testing |
| **Vision obstacle overlay** | Built, tested, and removed | Robot broadcasts raw AI candidates (3-6x more than app shows), not confirmed detections. Unusable for map overlay. |
| **Patrol / cruise mode** | Topics identified in APK | Not yet probed; depends on camera working first |
| **Custom clean settings** | Protocol known | Not yet exposed in HA UI |

Camera snapshot and LED entities will be added once the AES decryption key is extracted from the Narwal APK.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect" during setup | Verify IP and that port 9002 is reachable. Robot must be powered on. |
| Entities show "Unavailable" | Robot may be asleep. Open Narwal app briefly to wake it. |
| Map not showing | Map loads after robot wakes. A new clean refreshes a stale map. |
| Commands not responding | Close the Narwal app — only one WebSocket connection at a time. |
| Z10 Ultra disconnects | Re-add the integration with the correct model selected. |

## Reporting Issues

Use the [issue templates](https://github.com/sjmotew/NarwalIntegration/issues/new/choose) — they collect your HA version, model, and debug logs for faster diagnosis.

## Disclaimer

This is an **unofficial**, community-developed integration — not affiliated with or endorsed by Narwal. The local protocol was reverse-engineered from network traffic and the Narwal mobile application.

- **Use at your own risk.** No warranty.
- **No cloud dependency.** No external data transmission.
- **Firmware updates** from Narwal may break this integration at any time.

## Contributing

Contributions and testing welcome! If you have a non-Flow Narwal model, testing reports are especially valuable.

## License

MIT
