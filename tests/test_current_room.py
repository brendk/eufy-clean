"""Current physical room follows map pixels and only signals room changes."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.robovac_mqtt.api.map_stream import MapData
from custom_components.robovac_mqtt.coordinator import EufyCleanCoordinator
from custom_components.robovac_mqtt.sensor import CurrentRoomSensorEntity


@pytest.fixture
def coordinator():
    coord = EufyCleanCoordinator(
        MagicMock(), MagicMock(),
        {"deviceId": "test", "deviceName": "Vacuum cleaner", "deviceModel": "T2351"},
    )
    # Asymmetric mask catches accidental Y inversion; left/right room split.
    coord._map_data = MapData(
        raw_pixels=b"", width=4, height=3, resolution=1,
        room_pixels=bytes(rid << 2 for rid in [7, 7, 8, 8, 7, 7, 8, 8, 9, 9, 9, 9]),
        room_outline_width=4, room_outline_height=3,
        room_names={7: "Bathroom", 8: "Hallway", 9: "Living Room"},
    )
    return coord


@pytest.mark.parametrize("pixel,expected", [
    ((0, 0), (7, "Bathroom")), ((3, 0), (8, "Hallway")),
    ((0, 2), (9, "Living Room")), ((3, 2), (9, "Living Room")),
    (None, (0, None)), ((-1, 0), (0, None)), ((4, 0), (0, None)),
])
def test_physical_room(coordinator, pixel, expected):
    coordinator._robot_pixel = pixel
    coordinator.data.robot_position_x = 14522
    coordinator.data.robot_position_y = 2410
    coordinator.data.active_room_ids = [8]
    assert coordinator.current_room() == expected


def test_missing_map_or_mask(coordinator):
    coordinator._robot_pixel = (0, 0)
    coordinator._map_data.room_pixels = None
    assert coordinator.current_room() == (0, None)
    coordinator._map_data = None
    assert coordinator.current_room() == (0, None)


@pytest.mark.parametrize("width,height", [(0, 3), (4, 0), (-1, 3)])
def test_invalid_dimensions(coordinator, width, height):
    coordinator._robot_pixel = (0, 0)
    coordinator._map_data.width = width
    coordinator._map_data.height = height
    assert coordinator.current_room() == (0, None)


def test_only_room_changes_signal(coordinator):
    coordinator.async_update_listeners = MagicMock()
    with patch("custom_components.robovac_mqtt.coordinator.async_dispatcher_send") as send:
        coordinator._robot_pixel = (0, 0)
        coordinator._update_current_room()
        coordinator._robot_pixel = (1, 1)
        coordinator._update_current_room()
        assert send.call_count == 1
        coordinator._robot_pixel = (2, 1)
        coordinator._update_current_room()
        assert send.call_count == 2
        coordinator._map_data.room_names[8] = "Renamed Hallway"
        coordinator._update_current_room()
        assert send.call_count == 3
        coordinator._robot_pixel = None
        coordinator._update_current_room()
        assert send.call_count == 4
        coordinator._update_current_room()
        assert send.call_count == 4
        coordinator.async_update_listeners.assert_not_called()


def test_sensor_values_and_unknown(coordinator):
    coordinator._robot_pixel = (0, 0)
    sensor = CurrentRoomSensorEntity(coordinator)
    assert sensor.unique_id == "test_current_room"
    assert sensor.native_value == "Bathroom"
    assert sensor.extra_state_attributes == {"room_id": 7, "room_name": "Bathroom"}
    coordinator._map_data.room_names.clear()
    assert sensor.native_value == "Room 7"
    coordinator.data.rooms = [{"id": 7, "name": "Bathroom"}]
    assert sensor.native_value == "Bathroom"
    coordinator._robot_pixel = None
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {"room_id": None, "room_name": None}
