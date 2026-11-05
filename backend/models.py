from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import time

class VehicleType(str, Enum):
    AMBULANCE_CRITICAL = "AMBULANCE_CRITICAL"   # Code Red: Cardiac/Trauma/Stroke (Priority 1)
    ORGAN_TRANSIT = "ORGAN_TRANSIT"             # Organ Transport (Priority 1)
    FIRE_ENGINE = "FIRE_ENGINE"                 # Fire Response (Priority 2)
    AMBULANCE_STANDARD = "AMBULANCE_STANDARD"   # Normal Patient Transport (Priority 3)
    POLICE_ESCORT = "POLICE_ESCORT"             # Police / Rapid Action (Priority 4)
    AMBULANCE = "AMBULANCE"                     # Standard 108 Emergency Ambulance alias
    FIRE_BRIGADE = "FIRE_BRIGADE"               # Fire Brigade Tender alias
    POLICE = "POLICE"                           # Police Interceptor alias

class ApproachDirection(str, Enum):
    NORTH = "NORTH"
    SOUTH = "SOUTH"
    EAST = "EAST"
    WEST = "WEST"
    INSIDE = "INSIDE"
    DEPARTED = "DEPARTED"

class LightColor(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"

class SystemMode(str, Enum):
    NORMAL_AUTO = "NORMAL_AUTO"
    PRE_EMPTION_YELLOW = "PRE_EMPTION_YELLOW"
    EMERGENCY_CORRIDOR = "EMERGENCY_CORRIDOR"
    POST_CLEARANCE = "POST_CLEARANCE"

class GPSCoordinate(BaseModel):
    lat: float = Field(..., description="Latitude in decimal degrees")
    lon: float = Field(..., description="Longitude in decimal degrees")
    speed_kmh: float = Field(0.0, description="Speed in km/h")
    heading: Optional[float] = Field(None, description="Bearing heading in degrees (0-360)")

class VehicleTelemetry(BaseModel):
    vehicle_id: str
    vehicle_type: VehicleType = VehicleType.AMBULANCE_CRITICAL
    priority_level: int = Field(1, ge=1, le=4, description="1 is highest priority, 4 is lowest")
    location: GPSCoordinate
    is_emergency_active: bool = True
    destination_hospital: Optional[str] = "KR Hospital Emergency Trauma, Mysuru"
    timestamp: float = Field(default_factory=time.time)

class DirectionSignal(BaseModel):
    direction: ApproachDirection
    color: LightColor
    countdown_seconds: int

class JunctionState(BaseModel):
    junction_id: str
    junction_name: str
    mode: SystemMode
    active_corridor: Optional[ApproachDirection] = None
    controlling_vehicle_id: Optional[str] = None
    priority_in_control: Optional[int] = None
    signals: Dict[str, LightColor]
    seconds_in_state: float
    geofence_meters: float
    detected_vehicles: List[Dict[str, Any]] = []
    log_messages: List[str] = []
