"""Tests for MapDisplayData.to_grid_coords() — live overlay coordinate transform.

Covers MAP-03 (live overlay / to_grid_coords) validation gaps:
  - Basic coordinate transform: pixel = raw - origin
  - Robot at origin returns (0, 0)
  - Real-world values produce expected grid coordinates
  - Edge cases: zero position, zero resolution
"""

from __future__ import annotations

from narwal_client.models import MapDisplayData


class TestToGridCoords:
    """Tests for MapDisplayData.to_grid_coords()."""

    def test_basic_transform(self) -> None:
        """pixel = raw - origin for both axes."""
        display = MapDisplayData(robot_x=10.0, robot_y=20.0)
        result = display.to_grid_coords(resolution=60, origin_x=-100, origin_y=-200)

        assert result is not None
        px, py = result
        # 10.0 - (-100) = 110.0
        assert abs(px - 110.0) < 0.01
        # 20.0 - (-200) = 220.0
        assert abs(py - 220.0) < 0.01

    def test_at_origin(self) -> None:
        """Robot at origin position returns (0, 0) grid coords."""
        # origin_x=-280, origin_y=-341: robot at (-280, -341) should give (0, 0)
        display = MapDisplayData(robot_x=-280.0, robot_y=-341.0)
        result = display.to_grid_coords(resolution=60, origin_x=-280, origin_y=-341)

        assert result is not None
        px, py = result
        assert abs(px) < 0.01
        assert abs(py) < 0.01

    def test_with_real_values(self) -> None:
        """Use known real values: origin=(-280,-341), dock raw=(-7.97, 1.25).

        Expected: ~(272, 342) grid coords.
        """
        display = MapDisplayData(robot_x=-7.97, robot_y=1.25)
        result = display.to_grid_coords(resolution=60, origin_x=-280, origin_y=-341)

        assert result is not None
        px, py = result
        # -7.97 - (-280) = 272.03
        assert abs(px - 272.03) < 0.1
        # 1.25 - (-341) = 342.25
        assert abs(py - 342.25) < 0.1

    def test_zero_position_returns_none(self) -> None:
        """Robot at (0.0, 0.0) is treated as 'no valid position'."""
        display = MapDisplayData(robot_x=0.0, robot_y=0.0)
        result = display.to_grid_coords(resolution=60, origin_x=-280, origin_y=-341)

        assert result is None

    def test_zero_resolution_returns_none(self) -> None:
        """Zero resolution means no valid transform."""
        display = MapDisplayData(robot_x=10.0, robot_y=20.0)
        result = display.to_grid_coords(resolution=0, origin_x=-280, origin_y=-341)

        assert result is None

    def test_negative_resolution_returns_none(self) -> None:
        """Negative resolution means no valid transform."""
        display = MapDisplayData(robot_x=10.0, robot_y=20.0)
        result = display.to_grid_coords(resolution=-1, origin_x=0, origin_y=0)

        assert result is None

    def test_positive_origin(self) -> None:
        """Positive origin values work correctly."""
        display = MapDisplayData(robot_x=50.0, robot_y=60.0)
        result = display.to_grid_coords(resolution=60, origin_x=10, origin_y=20)

        assert result is not None
        px, py = result
        # 50.0 - 10 = 40.0
        assert abs(px - 40.0) < 0.01
        # 60.0 - 20 = 40.0
        assert abs(py - 40.0) < 0.01


class TestMapDisplayDataFromBroadcast:
    """Tests for MapDisplayData.from_broadcast() parsing."""

    def test_basic_parsing(self) -> None:
        """Parse robot position from broadcast payload."""
        decoded = {
            "1": {
                "1": {"1": -7.97, "2": 1.25},
                "2": 1.5708,  # ~90 degrees in radians
            },
            "5": {
                "1": {"1": -8.0, "2": 0.22},
            },
            "10": 1709900000000,
        }
        result = MapDisplayData.from_broadcast(decoded)

        assert abs(result.robot_x - (-7.97)) < 0.01
        assert abs(result.robot_y - 1.25) < 0.01
        assert abs(result.robot_heading - 90.0) < 1.0  # radians -> degrees
        assert abs(result.dock_ref_x - (-8.0)) < 0.01
        assert abs(result.dock_ref_y - 0.22) < 0.01
        assert result.timestamp == 1709900000000

    def test_empty_broadcast(self) -> None:
        """Empty broadcast returns default values."""
        result = MapDisplayData.from_broadcast({})
        assert result.robot_x == 0.0
        assert result.robot_y == 0.0
        assert result.timestamp == 0
