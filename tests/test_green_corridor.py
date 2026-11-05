import time
from backend.engine import (
    haversine_distance_meters,
    determine_approach_direction,
    GreenCorridorJunction
)
from backend.models import (
    VehicleTelemetry,
    VehicleType,
    ApproachDirection,
    SystemMode,
    LightColor,
    GPSCoordinate
)

def test_haversine_distance():
    # Delhi AIIMS (28.5672, 77.2100) to a point ~500m North (approx 28.5717, 77.2100)
    lat1, lon1 = 28.5672, 77.2100
    lat2, lon2 = 28.5717, 77.2100
    dist = haversine_distance_meters(lat1, lon1, lat2, lon2)
    assert 480 <= dist <= 520

def test_determine_approach_direction():
    junc_lat, junc_lon = 28.5672, 77.2100
    
    # 500m North
    north_lat, north_lon = 28.5717, 77.2100
    dir_n = determine_approach_direction(north_lat, north_lon, junc_lat, junc_lon, 500)
    assert dir_n == ApproachDirection.NORTH

    # 500m South
    south_lat, south_lon = 28.5627, 77.2100
    dir_s = determine_approach_direction(south_lat, south_lon, junc_lat, junc_lon, 500)
    assert dir_s == ApproachDirection.SOUTH

    # 500m East
    east_lat, east_lon = 28.5672, 77.2151
    dir_e = determine_approach_direction(east_lat, east_lon, junc_lat, junc_lon, 500)
    assert dir_e == ApproachDirection.EAST

    # 500m West
    west_lat, west_lon = 28.5672, 77.2049
    dir_w = determine_approach_direction(west_lat, west_lon, junc_lat, junc_lon, 500)
    assert dir_w == ApproachDirection.WEST

def test_emergency_preemption_lifecycle():
    junction = GreenCorridorJunction(geofence_meters=500.0, yellow_duration_sec=0.1)
    
    # Initially Normal Auto mode
    assert junction.mode == SystemMode.NORMAL_AUTO
    lights = junction.get_signal_lights()
    assert LightColor.GREEN in lights.values()

    # Ambulance approaches from 800m North (Outside geofence)
    telem_800m = VehicleTelemetry(
        vehicle_id="AMB-108-TEST",
        vehicle_type=VehicleType.AMBULANCE_CRITICAL,
        priority_level=1,
        location=GPSCoordinate(lat=28.5744, lon=77.2100, speed_kmh=60.0), # ~800m
        is_emergency_active=True
    )
    junction.update_vehicle_telemetry(telem_800m)
    junction.tick()
    # Still normal mode
    assert junction.mode == SystemMode.NORMAL_AUTO

    # Ambulance enters 450m (Inside 500m geofence)
    telem_450m = VehicleTelemetry(
        vehicle_id="AMB-108-TEST",
        vehicle_type=VehicleType.AMBULANCE_CRITICAL,
        priority_level=1,
        location=GPSCoordinate(lat=28.5712, lon=77.2100, speed_kmh=60.0), # ~450m
        is_emergency_active=True
    )
    junction.update_vehicle_telemetry(telem_450m)
    junction.tick()

    # Should transition to PRE_EMPTION_YELLOW
    assert junction.mode == SystemMode.PRE_EMPTION_YELLOW

    # Wait for yellow safety transition
    time.sleep(0.15)
    junction.tick()

    # Now should be in EMERGENCY_CORRIDOR
    assert junction.mode == SystemMode.EMERGENCY_CORRIDOR
    assert junction.active_corridor == ApproachDirection.NORTH

    # Check signal lights: North must be GREEN, others RED
    lights = junction.get_signal_lights()
    assert lights["NORTH"] == LightColor.GREEN
    assert lights["EAST"] == LightColor.RED
    assert lights["SOUTH"] == LightColor.RED
    assert lights["WEST"] == LightColor.RED

def test_priority_arbitration():
    junction = GreenCorridorJunction(geofence_meters=500.0, yellow_duration_sec=0.05)

    # Fire Engine (Priority 2) at 400m East
    fire_telem = VehicleTelemetry(
        vehicle_id="FIRE-101",
        vehicle_type=VehicleType.FIRE_ENGINE,
        priority_level=2,
        location=GPSCoordinate(lat=28.5672, lon=77.2141, speed_kmh=50.0),
        is_emergency_active=True
    )
    junction.update_vehicle_telemetry(fire_telem)

    # Cardiac Ambulance (Priority 1) at 450m North
    amb_telem = VehicleTelemetry(
        vehicle_id="AMB-108-CRITICAL",
        vehicle_type=VehicleType.AMBULANCE_CRITICAL,
        priority_level=1,
        location=GPSCoordinate(lat=28.5712, lon=77.2100, speed_kmh=60.0),
        is_emergency_active=True
    )
    junction.update_vehicle_telemetry(amb_telem)

    junction.tick()
    # Priority 1 Ambulance must win over Priority 2 Fire Engine
    best_candidate = junction._select_highest_priority_candidate()
    assert best_candidate is not None
    vid, vdata = best_candidate
    assert vid == "AMB-108-CRITICAL"
    assert vdata["direction"] == ApproachDirection.NORTH
