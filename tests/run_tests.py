import unittest
import time
import sys
import os

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tests.test_ml_pipeline import TestMLPipeline

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
from backend.corridor_router import (
    calculate_glosa_advisory,
    arbitrate_multi_vehicle,
    calculate_queue_flush,
    VehicleCandidate
)

class TestGreenCorridorSystem(unittest.TestCase):

    def test_haversine_distance(self):
        lat1, lon1 = 12.3168, 76.6508
        lat2, lon2 = 12.3213, 76.6508
        dist = haversine_distance_meters(lat1, lon1, lat2, lon2)
        self.assertTrue(480 <= dist <= 520, f"Calculated distance {dist} outside expected range [480, 520]")

    def test_approach_directions(self):
        junc_lat, junc_lon = 12.3168, 76.6508
        
        # North
        dir_n = determine_approach_direction(12.3213, 76.6508, junc_lat, junc_lon, 500)
        self.assertEqual(dir_n, ApproachDirection.NORTH)

        # South
        dir_s = determine_approach_direction(12.3123, 76.6508, junc_lat, junc_lon, 500)
        self.assertEqual(dir_s, ApproachDirection.SOUTH)

        # East
        dir_e = determine_approach_direction(12.3168, 76.6554, junc_lat, junc_lon, 500)
        self.assertEqual(dir_e, ApproachDirection.EAST)

        # West
        dir_w = determine_approach_direction(12.3168, 76.6462, junc_lat, junc_lon, 500)
        self.assertEqual(dir_w, ApproachDirection.WEST)

    def test_emergency_preemption_lifecycle(self):
        junction = GreenCorridorJunction(geofence_meters=500.0, yellow_duration_sec=0.1)
        self.assertEqual(junction.mode, SystemMode.NORMAL_AUTO)

        # Outside Geofence (800m North)
        telem_800m = VehicleTelemetry(
            vehicle_id="AMB-108-TEST",
            vehicle_type=VehicleType.AMBULANCE_CRITICAL,
            priority_level=1,
            location=GPSCoordinate(lat=12.3240, lon=76.6508, speed_kmh=60.0),
            is_emergency_active=True
        )
        junction.update_vehicle_telemetry(telem_800m)
        junction.tick()
        self.assertEqual(junction.mode, SystemMode.NORMAL_AUTO)

        # Inside Geofence (450m North)
        telem_450m = VehicleTelemetry(
            vehicle_id="AMB-108-TEST",
            vehicle_type=VehicleType.AMBULANCE_CRITICAL,
            priority_level=1,
            location=GPSCoordinate(lat=12.3208, lon=76.6508, speed_kmh=60.0),
            is_emergency_active=True
        )
        junction.update_vehicle_telemetry(telem_450m)
        junction.tick()
        self.assertEqual(junction.mode, SystemMode.PRE_EMPTION_YELLOW)

        # Safety Yellow expiration
        time.sleep(0.15)
        junction.tick()
        self.assertEqual(junction.mode, SystemMode.EMERGENCY_CORRIDOR)
        self.assertEqual(junction.active_corridor, ApproachDirection.NORTH)

        # Check Lights
        lights = junction.get_signal_lights()
        self.assertEqual(lights["NORTH"], LightColor.GREEN)
        self.assertEqual(lights["EAST"], LightColor.RED)
        self.assertEqual(lights["SOUTH"], LightColor.RED)
        self.assertEqual(lights["WEST"], LightColor.RED)

    def test_priority_arbitration(self):
        junction = GreenCorridorJunction(geofence_meters=500.0, yellow_duration_sec=0.05)

        # Fire Engine (Priority 2, 400m East)
        fire_telem = VehicleTelemetry(
            vehicle_id="FIRE-101",
            vehicle_type=VehicleType.FIRE_ENGINE,
            priority_level=2,
            location=GPSCoordinate(lat=12.3168, lon=76.6545, speed_kmh=50.0),
            is_emergency_active=True
        )
        junction.update_vehicle_telemetry(fire_telem)

        # Cardiac Ambulance (Priority 1, 450m North)
        amb_telem = VehicleTelemetry(
            vehicle_id="AMB-108-CRITICAL",
            vehicle_type=VehicleType.AMBULANCE_CRITICAL,
            priority_level=1,
            location=GPSCoordinate(lat=12.3208, lon=76.6508, speed_kmh=60.0),
            is_emergency_active=True
        )
        junction.update_vehicle_telemetry(amb_telem)

        best_candidate = junction._select_highest_priority_candidate()
        self.assertIsNotNone(best_candidate)
        vid, vdata = best_candidate
        self.assertEqual(vid, "AMB-108-CRITICAL")
        self.assertEqual(vdata["direction"], ApproachDirection.NORTH)

    def test_glosa_speed_advisory_clamping(self):
        # Case 1: High speed needed -> clamped to 65.0 km/h
        # 300m in 10s = 30 m/s = 108 km/h -> clamped to 65 km/h
        res_fast = calculate_glosa_advisory(distance_m=300.0, next_green_time=20.0, cur_time=10.0)
        self.assertEqual(res_fast["target_speed_kmh"], 65.0)
        self.assertTrue(res_fast["raw_calculated_speed_kmh"] > 65.0)

        # Case 2: Slow speed -> clamped to 35.0 km/h
        # 100m in 30s = 3.33 m/s = 12 km/h -> clamped to 35 km/h
        res_slow = calculate_glosa_advisory(distance_m=100.0, next_green_time=40.0, cur_time=10.0)
        self.assertEqual(res_slow["target_speed_kmh"], 35.0)
        self.assertTrue(res_slow["raw_calculated_speed_kmh"] < 35.0)

        # Case 3: In-range speed: 150m in 10.8s = 13.88 m/s = 50.0 km/h
        res_mid = calculate_glosa_advisory(distance_m=150.0, next_green_time=20.8, cur_time=10.0)
        self.assertTrue(45.0 <= res_mid["target_speed_kmh"] <= 55.0)

    def test_multi_vehicle_arbitration_j2(self):
        v1 = VehicleCandidate(
            vehicle_id="FIRE-02",
            vehicle_type="FIRE_BRIGADE",
            tier=2,
            distance_to_j2=150.0,
            speed_kmh=50.0,
            approach_direction="NORTH"
        )
        v2 = VehicleCandidate(
            vehicle_id="AMB-108-ICU",
            vehicle_type="AMBULANCE",
            tier=1,
            distance_to_j2=180.0,
            speed_kmh=55.0,
            approach_direction="WEST"
        )
        v3 = VehicleCandidate(
            vehicle_id="POLICE-09",
            vehicle_type="POLICE",
            tier=3,
            distance_to_j2=120.0,
            speed_kmh=45.0,
            approach_direction="EAST"
        )

        result = arbitrate_multi_vehicle([v1, v2, v3], junction_id="J2")
        # Tier 1 (Cardiac ICU) must win over Tier 2 and Tier 3
        self.assertEqual(result["primary_vehicle_id"], "AMB-108-ICU")
        self.assertEqual(result["primary_tier"], 1)
        # Secondary unit must be Tier 2 Fire Tender
        self.assertEqual(result["secondary_vehicle_id"], "FIRE-02")
        self.assertEqual(result["secondary_tier"], 2)
        self.assertIsNotNone(result["scheduled_secondary_clearance_sec"])
        self.assertTrue(result["scheduled_secondary_clearance_sec"] > 0)

    def test_cctv_queue_flush_logic(self):
        cctv_queues = {"N": 10, "S": 22, "E": 5, "W": 4}
        res = calculate_queue_flush(cctv_queues, junction_id="J2", ev_axis="EW")
        # For East-West corridor, cross streets are N and S; S has 22 vehicles (max)
        self.assertEqual(res["flush_direction"], "S")
        self.assertEqual(res["max_cctv_queue_detected"], 22)
        # Green time = 12 + 22 * 1.25 = 39.5, clamped to max 28.0s
        self.assertEqual(res["extended_green_seconds"], 28.0)

if __name__ == "__main__":
    unittest.main()
