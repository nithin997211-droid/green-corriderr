import time
from typing import Dict, List, Optional, Tuple
from .models import VehicleTelemetry, VehicleType, GPSCoordinate
from .engine import GreenCorridorJunction

# Latitude/Longitude degree offsets for Mysuru (~12.3168, 76.6508)
# 1 degree latitude ~= 111,320 meters
# 1 degree longitude ~= 111,320 * cos(12.3168°) ~= 108,757 meters
METERS_PER_LAT_DEG = 111320.0
METERS_PER_LON_DEG = 108757.0

class SimulationVehicle:
    def __init__(
        self,
        vehicle_id: str,
        vehicle_type: VehicleType,
        priority: int,
        start_direction: str,  # "NORTH", "SOUTH", "EAST", "WEST"
        initial_distance_meters: float = 850.0,
        speed_kmh: float = 65.0,
        destination: str = "KR Hospital Emergency Trauma, Mysuru"
    ):
        self.vehicle_id = vehicle_id
        self.vehicle_type = vehicle_type
        self.priority = priority
        self.start_direction = start_direction
        self.distance_from_center = initial_distance_meters
        self.speed_kmh = speed_kmh
        self.destination = destination
        self.is_active = True
        self.has_crossed = False

    def step(self, delta_seconds: float):
        """Advance the vehicle position toward or past the junction"""
        speed_mps = (self.speed_kmh * 1000.0) / 3600.0
        distance_moved = speed_mps * delta_seconds

        if not self.has_crossed:
            self.distance_from_center -= distance_moved
            if self.distance_from_center <= 0:
                self.has_crossed = True
                self.distance_from_center = abs(self.distance_from_center)
        else:
            # Moving away past junction
            self.distance_from_center += distance_moved

    def get_coordinates(self, junction_lat: float, junction_lon: float) -> Tuple[float, float, float]:
        """
        Returns (lat, lon, heading) based on distance and direction.
        """
        dist = self.distance_from_center
        if self.start_direction == "NORTH":
            # If approaching from North, vehicle is north (+lat), moving south (heading 180)
            # If crossed, moving south (-lat)
            if not self.has_crossed:
                lat = junction_lat + (dist / METERS_PER_LAT_DEG)
                lon = junction_lon
                heading = 180.0
            else:
                lat = junction_lat - (dist / METERS_PER_LAT_DEG)
                lon = junction_lon
                heading = 180.0
        elif self.start_direction == "SOUTH":
            if not self.has_crossed:
                lat = junction_lat - (dist / METERS_PER_LAT_DEG)
                lon = junction_lon
                heading = 0.0
            else:
                lat = junction_lat + (dist / METERS_PER_LAT_DEG)
                lon = junction_lon
                heading = 0.0
        elif self.start_direction == "EAST":
            if not self.has_crossed:
                lat = junction_lat
                lon = junction_lon + (dist / METERS_PER_LON_DEG)
                heading = 270.0
            else:
                lat = junction_lat
                lon = junction_lon - (dist / METERS_PER_LON_DEG)
                heading = 270.0
        else:  # WEST
            if not self.has_crossed:
                lat = junction_lat
                lon = junction_lon - (dist / METERS_PER_LON_DEG)
                heading = 90.0
            else:
                lat = junction_lat
                lon = junction_lon + (dist / METERS_PER_LON_DEG)
                heading = 90.0

        return lat, lon, heading

    def to_telemetry(self, junction_lat: float, junction_lon: float) -> VehicleTelemetry:
        lat, lon, heading = self.get_coordinates(junction_lat, junction_lon)
        return VehicleTelemetry(
            vehicle_id=self.vehicle_id,
            vehicle_type=self.vehicle_type,
            priority_level=self.priority,
            location=GPSCoordinate(
                lat=lat,
                lon=lon,
                speed_kmh=self.speed_kmh,
                heading=heading
            ),
            is_emergency_active=self.is_active,
            destination_hospital=self.destination,
            timestamp=time.time()
        )

class SimulationManager:
    """Manages active simulation vehicles and injects them into the junction engine."""
    def __init__(self, junction: GreenCorridorJunction):
        self.junction = junction
        self.sim_vehicles: Dict[str, SimulationVehicle] = {}
        self.is_running = True
        self.last_update = time.time()

    def spawn_preset(self, scenario_name: str):
        """Spawn predefined emergency scenarios"""
        if scenario_name == "ambulance_north":
            self.sim_vehicles["AMB-108-MYS-NORTH"] = SimulationVehicle(
                vehicle_id="AMB-108-MYS-01",
                vehicle_type=VehicleType.AMBULANCE_CRITICAL,
                priority=1,
                start_direction="NORTH",
                initial_distance_meters=850.0,
                speed_kmh=65.0,
                destination="KR Hospital Emergency Trauma, Mysuru"
            )
        elif scenario_name == "fire_engine_east":
            self.sim_vehicles["FIRE-101-MYS-EAST"] = SimulationVehicle(
                vehicle_id="FIRE-101-MYS-09",
                vehicle_type=VehicleType.FIRE_ENGINE,
                priority=2,
                start_direction="EAST",
                initial_distance_meters=800.0,
                speed_kmh=55.0,
                destination="Sayyaji Rao Road Commercial Fire"
            )
        elif scenario_name == "dual_conflict":
            # Priority 1 Ambulance from North, Priority 2 Fire Engine from East
            self.sim_vehicles["AMB-108-CRITICAL"] = SimulationVehicle(
                vehicle_id="AMB-108-CRITICAL",
                vehicle_type=VehicleType.AMBULANCE_CRITICAL,
                priority=1,
                start_direction="NORTH",
                initial_distance_meters=700.0,
                speed_kmh=65.0,
                destination="KR Hospital Emergency Trauma, Mysuru"
            )
            self.sim_vehicles["FIRE-TENDER-05"] = SimulationVehicle(
                vehicle_id="FIRE-TENDER-05",
                vehicle_type=VehicleType.FIRE_ENGINE,
                priority=2,
                start_direction="EAST",
                initial_distance_meters=750.0,
                speed_kmh=50.0,
                destination="Suburban Bus Stand Scene"
            )
            self.sim_vehicles["FIRE-TENDER-05"].distance_from_center = 750.0
            self.sim_vehicles["FIRE-TENDER-05"].start_direction = "EAST"

        elif scenario_name == "ambulance_south":
            self.sim_vehicles["AMB-102-MYS-SOUTH"] = SimulationVehicle(
                vehicle_id="AMB-102-MYS-44",
                vehicle_type=VehicleType.ORGAN_TRANSIT,
                priority=1,
                start_direction="SOUTH",
                initial_distance_meters=820.0,
                speed_kmh=75.0,
                destination="Apollo BGS Hospital, Kuvempunagar"
            )
        elif scenario_name == "ambulance_west":
            self.sim_vehicles["AMB-108-DL-WEST"] = SimulationVehicle(
                vehicle_id="AMB-108-WEST-02",
                vehicle_type=VehicleType.AMBULANCE_STANDARD,
                priority=3,
                start_direction="WEST",
                initial_distance_meters=750.0,
                speed_kmh=58.0,
                destination="Max Super Speciality Hospital"
            )

    def clear_all(self):
        self.sim_vehicles.clear()

    def update_step(self):
        now = time.time()
        delta = now - self.last_update
        self.last_update = now

        # Limit delta to sensible bounds
        delta = min(delta, 1.0)

        vehicles_to_remove = []
        for vid, sveh in self.sim_vehicles.items():
            sveh.step(delta)
            # If vehicle has crossed and is > 200m away, remove it from simulation
            if sveh.has_crossed and sveh.distance_from_center > 250.0:
                vehicles_to_remove.append(vid)
                continue

            telemetry = sveh.to_telemetry(self.junction.center_lat, self.junction.center_lon)
            self.junction.update_vehicle_telemetry(telemetry)

        for vid in vehicles_to_remove:
            del self.sim_vehicles[vid]
