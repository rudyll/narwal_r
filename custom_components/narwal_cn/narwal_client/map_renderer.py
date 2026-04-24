"""Map renderer for Narwal vacuum — converts raw map data to PNG bytes.

Pure Python module with no Home Assistant dependencies.
Uses Pillow for image rendering.

Map data format (confirmed from live robot data):
  - Compressed with standard zlib (header 78 01)
  - Decompressed data is a protobuf message: field 1 = packed repeated varints
  - Skip 4-byte protobuf header, then decode varints
  - Each varint encodes: room_id = value >> 8, pixel_type = value & 0xFF
  - Value 0 = unknown/outside, 0x20 = unassigned floor, 0x28 = unassigned obstacle
  - pixel_type & 0x10 = wall/border edge (darken the room color)
"""

from __future__ import annotations

import io
import logging
import zlib

_LOGGER = logging.getLogger(__name__)

# Room color palette (RGB) — up to 22 rooms
ROOM_COLORS: list[tuple[int, int, int]] = [
    (100, 149, 237),  # 1 - cornflower blue
    (144, 238, 144),  # 2 - light green
    (255, 182, 193),  # 3 - light pink
    (255, 218, 185),  # 4 - peach
    (221, 160, 221),  # 5 - plum
    (176, 224, 230),  # 6 - powder blue
    (255, 255, 150),  # 7 - light yellow
    (188, 143, 143),  # 8 - rosy brown
    (152, 251, 152),  # 9 - pale green
    (135, 206, 250),  # 10 - light sky blue
    (240, 128, 128),  # 11 - light coral
    (216, 191, 216),  # 12 - thistle
    (250, 250, 210),  # 13 - light goldenrod
    (173, 216, 230),  # 14 - light blue
    (244, 164, 96),   # 15 - sandy brown
    (245, 222, 179),  # 16 - wheat
    (127, 255, 212),  # 17 - aquamarine
    (255, 160, 122),  # 18 - light salmon
    (186, 218, 160),  # 19 - light green 2
    (255, 228, 196),  # 20 - bisque
    (200, 162, 200),  # 21 - light purple
    (174, 198, 207),  # 22 - pastel blue
]

# Obstacle/furniture annotation colors by catalog from APK map_furniture.json
OBSTACLE_COLORS: dict[int, tuple[int, int, int]] = {
    # Beds (1-3)
    1: (180, 140, 100),    # single bed - tan
    2: (180, 140, 100),    # double bed - tan
    3: (180, 140, 100),    # baby bed - tan
    # Tables (4-7, 31)
    4: (160, 130, 90),     # dining table - brown
    5: (160, 130, 90),     # round table - brown
    6: (160, 130, 90),     # tea table - brown
    7: (160, 130, 90),     # round tea table - brown
    31: (160, 130, 90),    # desk - brown
    # Cupboards/storage (8-12)
    8: (140, 120, 100),    # TV stand - dark tan
    9: (140, 120, 100),    # bedside table - dark tan
    10: (140, 120, 100),   # locker - dark tan
    11: (140, 120, 100),   # wardrobe - dark tan
    12: (140, 120, 100),   # shoe cabinet - dark tan
    # Sofas/chairs (13-18, 30)
    13: (100, 160, 130),   # armchair - sage
    14: (100, 160, 130),   # sofa - sage
    15: (100, 160, 130),   # L-shaped sofa - sage
    16: (100, 160, 130),   # lazy chair - sage
    17: (100, 160, 130),   # chair - sage
    18: (100, 160, 130),   # bar chair - sage
    30: (100, 160, 130),   # U-shaped sofa - sage
    # Pets (19-21, 75-76)
    19: (200, 160, 120),   # cat toilet - peach
    20: (200, 160, 120),   # pet feeder - peach
    21: (200, 160, 120),   # pet house - peach
    75: (200, 160, 120),   # cat house - peach
    76: (200, 160, 120),   # dog house - peach
    # Appliances (22-25, 34)
    22: (150, 180, 200),   # washing machine - steel blue
    23: (150, 180, 200),   # refrigerator - steel blue
    24: (150, 180, 200),   # air conditioner - steel blue
    25: (150, 180, 200),   # fan - steel blue
    34: (150, 180, 200),   # stove - steel blue
    # Bathroom (28, 33)
    28: (120, 180, 220),   # toilet - light blue
    33: (120, 180, 220),   # washbasin - light blue
    # Misc (26-27, 29, 32, 77-78)
    26: (100, 180, 100),   # potted plant - green
    27: (200, 200, 220),   # floor mirror - silver
    29: (80, 80, 80),      # piano - dark gray
    32: (80, 80, 80),      # grand piano - dark gray
    77: (200, 200, 200),   # round placeholder - gray
    78: (200, 200, 200),   # weighing scale - gray
}
OBSTACLE_COLOR_DEFAULT = (200, 200, 200)

# Special pixel colors
COLOR_UNKNOWN = (40, 40, 40)         # outside map / unmapped
COLOR_UNASSIGNED_FLOOR = (200, 200, 200)  # floor not assigned to a room
COLOR_UNASSIGNED_OBSTACLE = (80, 80, 80)  # obstacle not in a room
COLOR_FALLBACK = (180, 180, 180)     # unknown room ID


def decompress_map(compressed: bytes) -> bytes:
    """Decompress map grid data using zlib.

    Args:
        compressed: Raw compressed bytes from the robot (zlib format, header 78 01).

    Returns:
        Decompressed bytes containing protobuf-wrapped pixel varints.
    """
    if not compressed:
        return b""

    # Try zlib auto-detect (wbits=47 handles zlib, gzip, and raw)
    try:
        return zlib.decompress(compressed, 47)
    except zlib.error:
        pass

    # Try zlib default
    try:
        return zlib.decompress(compressed)
    except zlib.error:
        pass

    # Try raw deflate
    try:
        return zlib.decompress(compressed, -15)
    except zlib.error:
        pass

    _LOGGER.warning(
        "Could not decompress map data (%d bytes), using raw", len(compressed)
    )
    return compressed


def _decode_packed_varints(data: bytes) -> list[int]:
    """Decode protobuf packed repeated varint field from decompressed map data.

    The decompressed data starts with a protobuf field header:
      byte 0: 0x0a (field 1, wire type 2 = length-delimited)
      bytes 1-3: varint length of the packed data

    After the header, the remaining bytes are packed varint pixel values.

    Args:
        data: Decompressed bytes from decompress_map().

    Returns:
        List of integer pixel values.
    """
    if len(data) < 4:
        return []

    # Skip protobuf header: field tag (1 byte) + length varint (variable)
    pos = 0
    if data[0] == 0x0A:  # field 1, wire type 2
        pos = 1
        # Skip the length varint
        while pos < len(data) and data[pos] & 0x80:
            pos += 1
        pos += 1  # skip the final byte of the length varint
    # else: try decoding from the start (no header)

    pixels: list[int] = []
    while pos < len(data):
        val = 0
        shift = 0
        while pos < len(data):
            b = data[pos]
            pos += 1
            val |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        pixels.append(val)

    return pixels


def lookup_room_at_grid(
    compressed: bytes,
    width: int,
    height: int,
    grid_x: float,
    grid_y: float,
) -> tuple[int, str]:
    """Look up the room_id at a grid pixel coordinate.

    Returns (room_id, description) where description is one of:
      "room_N" for a valid room, "(empty)" for val=0,
      "(unassigned)" for 0x20/0x28, "(out_of_bounds)" if off grid.
    """
    px = int(grid_x)
    py = int(grid_y)
    if px < 0 or px >= width or py < 0 or py >= height:
        return (-1, f"(out_of_bounds: {px},{py} vs {width}x{height})")

    decompressed = decompress_map(compressed)
    if not decompressed:
        return (-1, "(no_data)")
    pixels = _decode_packed_varints(decompressed)

    idx = py * width + px
    if idx >= len(pixels):
        return (-1, f"(idx_overflow: {idx} >= {len(pixels)})")

    val = pixels[idx]
    if val == 0:
        return (0, "(empty)")
    if val in (0x20, 0x28):
        return (0, "(unassigned)")
    room_id = val >> 8
    ptype = val & 0xFF
    wall = " wall" if ptype & 0x10 else ""
    return (room_id, f"room_{room_id}{wall}")


def _darken(color: tuple[int, int, int], amount: int = 80) -> tuple[int, int, int]:
    """Darken an RGB color by subtracting from each channel."""
    return (
        max(0, color[0] - amount),
        max(0, color[1] - amount),
        max(0, color[2] - amount),
    )


def _draw_dock(
    draw: "ImageDraw.ImageDraw",
    dock_x: int,
    dock_y: int,
    size: int = 6,
) -> None:
    """Draw a dock/charging station icon at the given grid coordinates.

    Renders as a small white filled circle (matching the Narwal app style).
    """
    radius = size // 2
    draw.ellipse(
        [dock_x - radius, dock_y - radius, dock_x + radius, dock_y + radius],
        fill=(255, 255, 255),
        outline=(180, 180, 180),
    )


def _draw_robot(
    draw: "ImageDraw.ImageDraw",
    rx: int,
    ry: int,
    heading: float | None,
    radius: int,
) -> None:
    """Draw robot position with optional heading arrow.

    Args:
        draw: PIL ImageDraw instance.
        rx: Robot X in image coordinates (already Y-flipped).
        ry: Robot Y in image coordinates (already Y-flipped).
        heading: Heading in degrees (0=right, 90=up in world coords).
            None to draw circle only without heading arrow.
        radius: Circle radius in pixels.
    """
    import math

    # Blue filled circle with white outline
    draw.ellipse(
        [rx - radius, ry - radius, rx + radius, ry + radius],
        fill=(0, 120, 255),
        outline=(255, 255, 255),
    )

    # Heading arrow — white line from center in heading direction
    if heading is not None:
        # Convert degrees to radians. Heading 0=right, 90=up in world coords.
        # Image Y is flipped (down = positive), so negate the Y component.
        rad = math.radians(heading)
        arrow_len = radius * 2.5
        dx = math.cos(rad) * arrow_len
        dy = -math.sin(rad) * arrow_len  # negate for image Y-down
        draw.line(
            [(rx, ry), (rx + dx, ry + dy)],
            fill=(255, 255, 255),
            width=2,
        )


def render_map_png(
    decompressed: bytes,
    width: int,
    height: int,
    robot_x: float | None = None,
    robot_y: float | None = None,
    robot_heading: float | None = None,
    dock_x: float | None = None,
    dock_y: float | None = None,
    room_names: dict[int, str] | None = None,
) -> bytes:
    """Render decompressed map data as a PNG image.

    Decodes the protobuf-packed varint pixel data and renders each pixel:
      - Value 0: unknown/outside (dark gray)
      - Value 0x20: unassigned floor (light gray)
      - Value 0x28: unassigned obstacle (dark gray)
      - Otherwise: room_id = value >> 8, pixel_type = value & 0xFF
        - pixel_type & 0x10: wall/border (darker shade of room color)
        - else: floor (room color)

    Args:
        decompressed: Decompressed map bytes (from decompress_map).
        width: Map width in pixels.
        height: Map height in pixels.
        robot_x: Robot X position in grid coordinates (optional).
        robot_y: Robot Y position in grid coordinates (optional).
        robot_heading: Robot heading in degrees (optional).
        dock_x: Dock X position in grid coordinates (optional).
        dock_y: Dock Y position in grid coordinates (optional).
        room_names: Mapping of room_id to display name (optional).

    Returns:
        PNG image as bytes, or empty bytes on failure.
    """
    if not decompressed or width <= 0 or height <= 0:
        return b""

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        _LOGGER.error("Pillow is required for map rendering")
        return b""

    pixels = _decode_packed_varints(decompressed)
    expected = width * height

    if len(pixels) < expected:
        _LOGGER.warning(
            "Map has %d pixels, expected %d (%dx%d) — padding",
            len(pixels), expected, width, height,
        )
        pixels.extend([0] * (expected - len(pixels)))
    elif len(pixels) > expected:
        pixels = pixels[:expected]

    img = Image.new("RGB", (width, height), COLOR_UNKNOWN)
    px = img.load()

    # Track room pixel sums for centroid computation
    room_sum_x: dict[int, int] = {}
    room_sum_y: dict[int, int] = {}
    room_count: dict[int, int] = {}

    for i, val in enumerate(pixels):
        x = i % width
        y = i // width

        if val == 0:
            continue  # already set to COLOR_UNKNOWN
        elif val == 0x20:
            px[x, y] = COLOR_UNASSIGNED_FLOOR
        elif val == 0x28:
            px[x, y] = COLOR_UNASSIGNED_OBSTACLE
        else:
            room_id = val >> 8
            ptype = val & 0xFF

            if 1 <= room_id <= len(ROOM_COLORS):
                base = ROOM_COLORS[room_id - 1]
            else:
                base = COLOR_FALLBACK

            if ptype & 0x10:  # wall/border edge
                px[x, y] = _darken(base)
            else:
                px[x, y] = base

            # Accumulate for centroid (floor pixels only, not walls)
            if room_names and room_id in room_names and not (ptype & 0x10):
                room_sum_x[room_id] = room_sum_x.get(room_id, 0) + x
                room_sum_y[room_id] = room_sum_y.get(room_id, 0) + y
                room_count[room_id] = room_count.get(room_id, 0) + 1

    # Flip vertically BEFORE drawing overlays — pixel data is stored with
    # Y increasing upward (math coordinates) but images render Y downward.
    # Overlays (labels, dock, robot) use flipped coordinates so text is right-side up.
    img = img.transpose(Image.FLIP_TOP_BOTTOM)

    draw = ImageDraw.Draw(img)

    # Draw room labels at flipped centroids
    if room_names:
        try:
            font = ImageFont.truetype("arial.ttf", 10)
        except (IOError, OSError):
            font = ImageFont.load_default()
        for rid, name in room_names.items():
            if not name or rid not in room_count:
                continue
            cx = room_sum_x[rid] // room_count[rid]
            cy = height - 1 - (room_sum_y[rid] // room_count[rid])
            bbox = font.getbbox(name)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = cx - tw // 2
            ty = cy - th // 2
            # Dark outline for readability
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                draw.text((tx + ox, ty + oy), name, fill=(0, 0, 0), font=font)
            draw.text((tx, ty), name, fill=(255, 255, 255), font=font)

    # Draw dock position (before robot so robot draws on top)
    # Flip dock Y to match the flipped image
    if dock_x is not None and dock_y is not None:
        dock_size = max(4, min(width, height) // 60)
        _draw_dock(draw, int(dock_x), height - 1 - int(dock_y), dock_size)

    # Draw robot position (flip Y) — skip if out of bounds
    if robot_x is not None and robot_y is not None:
        rx = int(robot_x)
        ry = height - 1 - int(robot_y)
        if 0 <= rx < width and 0 <= ry < height:
            radius = max(3, min(width, height) // 80)
            _draw_robot(draw, rx, ry, robot_heading, radius)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_base_map(
    compressed: bytes,
    width: int,
    height: int,
    dock_x: float | None = None,
    dock_y: float | None = None,
    room_names: dict[int, str] | None = None,
    obstacles: "list | None" = None,
    origin_x: int = 0,
    origin_y: int = 0,
) -> "Image.Image | None":
    """Render the static floor plan as a PIL Image (no robot overlay).

    Returns a PIL Image that can be cached and reused across frames.
    Only needs to be re-rendered when the static map data changes.

    Args:
        obstacles: List of ObstacleInfo objects to render (optional).
        origin_x: Map origin X offset for obstacle coordinate transform.
        origin_y: Map origin Y offset for obstacle coordinate transform.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        _LOGGER.error("Pillow is required for map rendering")
        return None

    decompressed = decompress_map(compressed)
    if not decompressed or width <= 0 or height <= 0:
        return None

    pixels = _decode_packed_varints(decompressed)
    expected = width * height

    if len(pixels) < expected:
        pixels.extend([0] * (expected - len(pixels)))
    elif len(pixels) > expected:
        pixels = pixels[:expected]

    img = Image.new("RGB", (width, height), COLOR_UNKNOWN)
    px = img.load()

    room_sum_x: dict[int, int] = {}
    room_sum_y: dict[int, int] = {}
    room_count: dict[int, int] = {}

    for i, val in enumerate(pixels):
        x = i % width
        y = i // width

        if val == 0:
            continue
        elif val == 0x20:
            px[x, y] = COLOR_UNASSIGNED_FLOOR
        elif val == 0x28:
            px[x, y] = COLOR_UNASSIGNED_OBSTACLE
        else:
            room_id = val >> 8
            ptype = val & 0xFF

            if 1 <= room_id <= len(ROOM_COLORS):
                base = ROOM_COLORS[room_id - 1]
            else:
                base = COLOR_FALLBACK

            if ptype & 0x10:
                px[x, y] = _darken(base)
            else:
                px[x, y] = base

            if room_names and room_id in room_names and not (ptype & 0x10):
                room_sum_x[room_id] = room_sum_x.get(room_id, 0) + x
                room_sum_y[room_id] = room_sum_y.get(room_id, 0) + y
                room_count[room_id] = room_count.get(room_id, 0) + 1

    img = img.transpose(Image.FLIP_TOP_BOTTOM)
    draw = ImageDraw.Draw(img)

    if room_names:
        try:
            font = ImageFont.truetype("arial.ttf", 10)
        except (IOError, OSError):
            font = ImageFont.load_default()
        for rid, name in room_names.items():
            if not name or rid not in room_count:
                continue
            cx = room_sum_x[rid] // room_count[rid]
            cy = height - 1 - (room_sum_y[rid] // room_count[rid])
            bbox = font.getbbox(name)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = cx - tw // 2
            ty = cy - th // 2
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                draw.text((tx + ox, ty + oy), name, fill=(0, 0, 0), font=font)
            draw.text((tx, ty), name, fill=(255, 255, 255), font=font)

    # Draw obstacle/furniture annotations (static data from get_map field 2.32)
    if obstacles:
        try:
            obs_font = ImageFont.truetype("arial.ttf", 8)
        except (IOError, OSError):
            obs_font = ImageFont.load_default()
        for obs in obstacles:
            gx, gy = obs.to_grid_coords(origin_x, origin_y)
            # Skip out-of-bounds obstacles
            if gx < 0 or gx >= width or gy < 0 or gy >= height:
                continue
            img_x = int(gx)
            img_y = height - 1 - int(gy)
            half_w = max(1, int(obs.width / 2))
            half_h = max(1, int(obs.height / 2))
            color = OBSTACLE_COLORS.get(obs.type_id, OBSTACLE_COLOR_DEFAULT)
            draw.rectangle(
                [img_x - half_w, img_y - half_h, img_x + half_w, img_y + half_h],
                outline=color, width=1,
            )
            # Draw label centered above the rectangle
            label = obs.display_name
            bbox = obs_font.getbbox(label)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            lx = img_x - tw // 2
            ly = img_y - half_h - th - 2
            # Dark outline for readability
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                draw.text((lx + ox, ly + oy), label, fill=(0, 0, 0), font=obs_font)
            draw.text((lx, ly), label, fill=color, font=obs_font)

    if dock_x is not None and dock_y is not None:
        dock_size = max(4, min(width, height) // 60)
        _draw_dock(draw, int(dock_x), height - 1 - int(dock_y), dock_size)

    return img


def render_overlay(
    base_img: "Image.Image",
    height: int,
    robot_x: float | None = None,
    robot_y: float | None = None,
    robot_heading: float | None = None,
    trail: list[tuple[float, float]] | None = None,
) -> bytes:
    """Draw robot position and trail on a copy of the cached base map.

    Args:
        base_img: Cached PIL Image from render_base_map (not modified).
        height: Map height in pixels (for Y-flip).
        robot_x: Robot X in grid coordinates.
        robot_y: Robot Y in grid coordinates.
        robot_heading: Heading in degrees.
        trail: List of (grid_x, grid_y) positions to draw as cleaning path.

    Returns:
        PNG bytes of the composited image.
    """
    from PIL import ImageDraw

    img = base_img.copy()
    draw = ImageDraw.Draw(img)
    width = img.width

    # Draw trail (blue path showing where robot has cleaned)
    if trail and len(trail) >= 2:
        recent_start = max(len(trail) - 200, 0)
        for i in range(len(trail) - 1):
            if i >= recent_start:
                color = (30, 120, 255)  # bright blue for recent
            else:
                color = (15, 60, 130)  # dim blue for older
            x1, y1 = int(trail[i][0]), height - 1 - int(trail[i][1])
            x2, y2 = int(trail[i + 1][0]), height - 1 - int(trail[i + 1][1])
            draw.line([(x1, y1), (x2, y2)], fill=color, width=2)

    # Draw robot
    if robot_x is not None and robot_y is not None:
        rx = int(robot_x)
        ry = height - 1 - int(robot_y)
        if 0 <= rx < width and 0 <= ry < height:
            radius = max(3, min(width, height) // 80)
            _draw_robot(draw, rx, ry, robot_heading, radius)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_map_from_compressed(
    compressed: bytes,
    width: int,
    height: int,
    robot_x: float | None = None,
    robot_y: float | None = None,
    robot_heading: float | None = None,
    dock_x: float | None = None,
    dock_y: float | None = None,
    room_names: dict[int, str] | None = None,
) -> bytes:
    """Decompress and render map data in one step (legacy interface).

    Args:
        compressed: Compressed map bytes from the robot.
        width: Map width in pixels.
        height: Map height in pixels.
        robot_x: Robot X position (optional).
        robot_y: Robot Y position (optional).
        robot_heading: Robot heading in degrees (optional).
        dock_x: Dock X position (optional).
        dock_y: Dock Y position (optional).
        room_names: Mapping of room_id to display name (optional).

    Returns:
        PNG image as bytes, or empty bytes on failure.
    """
    decompressed = decompress_map(compressed)
    return render_map_png(
        decompressed, width, height, robot_x, robot_y, robot_heading,
        dock_x, dock_y, room_names,
    )
