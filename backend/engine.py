import math
import time
from typing import Dict, List, Optional, Tuple, Any
from .models import (
    VehicleTelemetry, ApproachDirection, LightColor, 
    SystemMode, JunctionState
)

def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes distance in meters between two (lat, lon) coordinates on Earth
    using the Haversine formula.
    """
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def calculate_bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes initial bearing heading from point 1 to point 2 in degrees (0 to 360).
    0 = North, 90 = East, 180 = South, 270 = West.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0

def determine_approach_direction(
    vehicle_lat: float, 
    vehicle_lon: float, 
    junction_lat: float, 
    junction_lon: float,
    distance_meters: float
) -> ApproachDirection:
    """
    Determines which junction branch the vehicle is currently located on.
    Calculates the vector from junction center to vehicle.
    """
    if distance_meters <= 20.0:
        return ApproachDirection.INSIDE

    # Bearing from junction center to vehicle
    bearing_from_junction = calculate_bearing_degrees(
        junction_lat, junction_lon, vehicle_lat, vehicle_lon
    )

    # 315 to 45 deg -> Vehicle is to the North
    if bearing_from_junction >= 315 or bearing_from_junction < 45:
        return ApproachDirection.NORTH
    # 45 to 135 deg -> Vehicle is to the East
    elif 45 <= bearing_from_junction < 135:
        return ApproachDirection.EAST
    # 135 to 225 deg -> Vehicle is to the South
    elif 135 <= bearing_from_junction < 225:
        return ApproachDirection.SOUTH
    # 225 to 315 deg -> Vehicle is to the West
    else:
        return ApproachDirection.WEST


class GreenCorridorJunction:
    """
    Intelligent Traffic Signal Controller with Emergency Vehicle Preemption (EVP)
    and Automated Priority Corridor Logic.
    """
    def __init__(
        self,
        junction_id: str = "MYS_KRHOSP_JUNC_01",
        junction_name: str = "KR Hospital - Irwin Road Junction, Mysuru",
        center_lat: float = 12.3168,
        center_lon: float = 76.6508,
        geofence_meters: float = 500.0,
        yellow_duration_sec: float = 3.0,
        max_corridor_timeout_sec: float = 90.0,
    ):
        self.junction_id = junction_id
        self.junction_name = junction_name
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.geofence_meters = geofence_meters
        self.yellow_duration_sec = yellow_duration_sec
        self.max_corridor_timeout_sec = max_corridor_timeout_sec

        # Regular cyclic signal state
        self.normal_cycle_order = [
            ApproachDirection.NORTH,
            ApproachDirection.EAST,
            ApproachDirection.SOUTH,
            ApproachDirection.WEST,
        ]
        self.normal_phase_index = 0
        self.normal_phase_duration = 15.0  # seconds per green phase in normal mode
        self.last_phase_change_time = time.time()

        # EVP State Machine
        self.mode = SystemMode.NORMAL_AUTO
        self.state_enter_time = time.time()
        self.active_corridor: Optional[ApproachDirection] = None
        self.target_corridor: Optional[ApproachDirection] = None
        self.controlling_vehicle: Optional[VehicleTelemetry] = None

        # Track active vehicles in proximity
        # vehicle_id -> {"telemetry": VehicleTelemetry, "distance": float, "direction": ApproachDirection, "last_seen": float, "previous_distance": float}
        self.tracked_vehicles: Dict[str, Dict[str, Any]] = {}

        # Log queue
        self.logs: List[str] = []
        self._add_log(f"System initialized at junction: {self.junction_name} (Geofence: {self.geofence_meters}m)")

    def _add_log(self, msg: str):
        timestamp_str = time.strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp_str}] {msg}")
        if len(self.logs) > 60:
            self.logs.pop(0)

    def update_vehicle_telemetry(self, telemetry: VehicleTelemetry) -> Dict[str, Any]:
        """
        Processes incoming GPS telemetry packet from an emergency vehicle.
        Computes distance, approach direction, and updates tracking table.
        """
        now = time.time()
        dist = haversine_distance_meters(
            telemetry.location.lat, telemetry.location.lon,
            self.center_lat, self.center_lon
        )
        direction = determine_approach_direction(
            telemetry.location.lat, telemetry.location.lon,
            self.center_lat, self.center_lon, dist
        )

        prev_info = self.tracked_vehicles.get(telemetry.vehicle_id)
        prev_dist = prev_info["distance"] if prev_info else dist
        is_approaching = dist < prev_dist if prev_info else True

        self.tracked_vehicles[telemetry.vehicle_id] = {
            "telemetry": telemetry,
            "distance": dist,
            "previous_distance": prev_dist,
            "direction": direction,
            "is_approaching": is_approaching,
            "last_seen": now
        }

        # Check if vehicle has just entered geofence
        if dist <= self.geofence_meters and telemetry.is_emergency_active:
            if not prev_info or prev_info["distance"] > self.geofence_meters:
                self._add_log(
                    f"🚨 GEOFENCE ALERT: {telemetry.vehicle_id} ({telemetry.vehicle_type.value}) "
                    f"entered {self.geofence_meters}m zone from {direction.value}! Dist: {dist:.1f}m"
                )

        return {
            "vehicle_id": telemetry.vehicle_id,
            "distance_meters": round(dist, 1),
            "approach_direction": direction.value,
            "is_approaching": is_approaching,
            "in_geofence": dist <= self.geofence_meters and telemetry.is_emergency_active
        }

    def _clean_stale_vehicles(self, now: float):
        """Remove vehicles that haven't broadcasted in > 20 seconds or are far away"""
        to_delete = []
        for vid, data in self.tracked_vehicles.items():
            if (now - data["last_seen"]) > 20.0 or data["distance"] > (self.geofence_meters * 2.5):
                to_delete.append(vid)
        for vid in to_delete:
            del self.tracked_vehicles[vid]

    def _select_highest_priority_candidate(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Selects the emergency vehicle that should claim the green corridor.
        Priority Rules:
        1. Must be within geofence and emergency siren active.
        2. Lower priority number wins (Priority 1 > Priority 2 > Priority 3).
        3. If priorities are equal, vehicle with closest distance wins.
        """
        candidates = []
        for vid, vdata in self.tracked_vehicles.items():
            telem = vdata["telemetry"]
            dist = vdata["distance"]
            if dist <= self.geofence_meters and telem.is_emergency_active:
                # Vehicle is a valid preemption candidate
                candidates.append((vid, vdata))

        if not candidates:
            return None

        def _v_rank(vtype: Any) -> int:
            s = str(vtype).upper()
            if "AMB" in s or "ORGAN" in s:
                return 1  # Highest priority: Emergency Medical
            if "FIRE" in s:
                return 2  # Second priority: Fire & Rescue
            if "POL" in s:
                return 3  # Lower priority: Police Interceptor (subordinate to EMS & Fire)
            return 2

        # Sort by (vehicle_type_rank ASC, priority_level ASC, distance_meters ASC)
        # Ambulance > Fire Tender > Police Interceptor
        candidates.sort(key=lambda item: (
            _v_rank(item[1]["telemetry"].vehicle_type),
            item[1]["telemetry"].priority_level,
            item[1]["distance"]
        ))
        return candidates[0]

    def tick(self) -> None:
        """
        Main state machine update loop. Call periodically (e.g. every 100ms - 500ms).
        """
        now = time.time()
        self._clean_stale_vehicles(now)
        time_in_state = now - self.state_enter_time

        # Candidate selection
        best_candidate = self._select_highest_priority_candidate()

        if self.mode == SystemMode.NORMAL_AUTO:
            if best_candidate:
                vid, vdata = best_candidate
                candidate_dir = vdata["direction"]
                self.controlling_vehicle = vdata["telemetry"]
                self.target_corridor = candidate_dir

                self._add_log(
                    f"⚡ PRE-EMPTION TRIGGERED: Emergency vehicle {vid} (Priority {self.controlling_vehicle.priority_level}) "
                    f"at {vdata['distance']:.1f}m. Initiating safety Yellow transition for {candidate_dir.value} corridor."
                )
                self.mode = SystemMode.PRE_EMPTION_YELLOW
                self.state_enter_time = now
            else:
                # Normal cyclic progression
                if time_in_state >= self.normal_phase_duration:
                    self.normal_phase_index = (self.normal_phase_index + 1) % len(self.normal_cycle_order)
                    self.state_enter_time = now

        elif self.mode == SystemMode.PRE_EMPTION_YELLOW:
            # Hold yellow on other directions for safety before turning full Green
            if time_in_state >= self.yellow_duration_sec:
                self.mode = SystemMode.EMERGENCY_CORRIDOR
                self.active_corridor = self.target_corridor
                self.state_enter_time = now
                self._add_log(
                    f"🟢 GREEN CORRIDOR ENGAGED for {self.active_corridor.value} arm! "
                    f"All conflicting lanes turned RED for {self.controlling_vehicle.vehicle_id}."
                )

        elif self.mode == SystemMode.EMERGENCY_CORRIDOR:
            # Check if controlling vehicle still exists
            ctrl_id = self.controlling_vehicle.vehicle_id if self.controlling_vehicle else None
            vdata = self.tracked_vehicles.get(ctrl_id) if ctrl_id else None

            # Conditions to release corridor:
            # 1. Vehicle has crossed the intersection and is moving away (> 35m past center or inside)
            cleared = False
            if vdata:
                dist = vdata["distance"]
                prev_dist = vdata["previous_distance"]
                # If vehicle is moving away and was previously inside or near
                if dist > prev_dist and dist > 35.0 and prev_dist < 40.0:
                    cleared = True
                    self._add_log(f"✅ CLEARANCE CONFIRMED: {ctrl_id} safely crossed junction ({dist:.1f}m past).")
                elif not vdata["telemetry"].is_emergency_active:
                    cleared = True
                    self._add_log(f"ℹ️ Emergency mode deactivated for {ctrl_id}.")
            else:
                # Lost signal or vehicle departed
                cleared = True
                self._add_log(f"ℹ️ Vehicle {ctrl_id} departed or signal lost. Releasing corridor.")

            # Watchdog timeout to prevent road gridlock
            timed_out = time_in_state >= self.max_corridor_timeout_sec
            if timed_out:
                self._add_log(f"⚠️ WATCHDOG TIMEOUT: Corridor timed out after {self.max_corridor_timeout_sec}s.")

            if cleared or timed_out:
                self.mode = SystemMode.POST_CLEARANCE
                self.state_enter_time = now

        elif self.mode == SystemMode.POST_CLEARANCE:
            # Hold all-red / safe yellow buffer before restoring normal traffic
            if time_in_state >= 3.0:
                self.mode = SystemMode.NORMAL_AUTO
                self.active_corridor = None
                self.target_corridor = None
                self.controlling_vehicle = None
                self.state_enter_time = now
                self._add_log("🔄 Normal cyclic traffic signal operation resumed.")

    def get_signal_lights(self) -> Dict[str, LightColor]:
        """
        Returns the current LightColor for each direction: NORTH, SOUTH, EAST, WEST.
        """
        signals = {
            ApproachDirection.NORTH.value: LightColor.RED,
            ApproachDirection.SOUTH.value: LightColor.RED,
            ApproachDirection.EAST.value: LightColor.RED,
            ApproachDirection.WEST.value: LightColor.RED,
        }

        if self.mode == SystemMode.NORMAL_AUTO:
            active_dir = self.normal_cycle_order[self.normal_phase_index]
            time_in_state = time.time() - self.state_enter_time
            # Show yellow during the last 3 seconds of a normal phase
            if time_in_state >= (self.normal_phase_duration - 3.0):
                signals[active_dir.value] = LightColor.YELLOW
            else:
                signals[active_dir.value] = LightColor.GREEN

        elif self.mode == SystemMode.PRE_EMPTION_YELLOW:
            # Flash yellow across all approaches to warn traffic of incoming emergency vehicle
            for d in signals:
                signals[d] = LightColor.YELLOW

        elif self.mode == SystemMode.EMERGENCY_CORRIDOR:
            # Emergency side gets bright GREEN; all other sides get absolute RED
            if self.active_corridor and self.active_corridor.value in signals:
                signals[self.active_corridor.value] = LightColor.GREEN
            # Opposite lane on the same straight corridor can also be given green or red based on policy.
            # In strict Indian VIP/Ambulance corridor, opposing side remains RED so emergency vehicle
            # can use full road / wrong lane if required to overtake blocked traffic!

        elif self.mode == SystemMode.POST_CLEARANCE:
            # All red or yellow caution for 3s recovery
            for d in signals:
                signals[d] = LightColor.YELLOW

        return signals

    def get_state_snapshot(self) -> JunctionState:
        """
        Builds a comprehensive real-time snapshot for the web dashboard and hardware clients.
        """
        now = time.time()
        detected_list = []
        for vid, data in self.tracked_vehicles.items():
            telem = data["telemetry"]
            detected_list.append({
                "vehicle_id": vid,
                "vehicle_type": telem.vehicle_type.value,
                "priority_level": telem.priority_level,
                "distance_meters": round(data["distance"], 1),
                "speed_kmh": round(telem.location.speed_kmh, 1),
                "approach_direction": data["direction"].value,
                "is_approaching": data["is_approaching"],
                "in_geofence": data["distance"] <= self.geofence_meters,
                "lat": telem.location.lat,
                "lon": telem.location.lon,
                "is_emergency_active": telem.is_emergency_active,
                "destination": telem.destination_hospital
            })

        # Sort detected vehicles by distance
        detected_list.sort(key=lambda x: x["distance_meters"])

        return JunctionState(
            junction_id=self.junction_id,
            junction_name=self.junction_name,
            mode=self.mode,
            active_corridor=self.active_corridor,
            controlling_vehicle_id=self.controlling_vehicle.vehicle_id if self.controlling_vehicle else None,
            priority_in_control=self.controlling_vehicle.priority_level if self.controlling_vehicle else None,
            signals=self.get_signal_lights(),
            seconds_in_state=round(now - self.state_enter_time, 1),
            geofence_meters=self.geofence_meters,
            detected_vehicles=detected_list,
            log_messages=self.logs[-15:]  # last 15 log entries
        )
