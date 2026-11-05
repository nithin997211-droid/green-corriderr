"""
Corridor Router: Green Light Optimal Speed Advisory (GLOSA),
Multi-Unit Emergency Vehicle Priority Arbitration, and Post-Preemption Queue Flush.

Part of the Green Corridor Intelligent Traffic Management System (Mysuru Edition).
"""

import time
from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/corridor", tags=["Corridor Routing & Preemption"])

# Standard Junction Spatial Model (Mysuru Arterial Corridor)
CORRIDOR_JUNCTIONS = {
    "J1": {
        "id": "J1",
        "name": "Ayurveda Hospital Circle",
        "lat": 12.3168,
        "lon": 76.6462,
        "canvas_x": 240,
        "cross_street": "Sayyaji Rao Road",
    },
    "J2": {
        "id": "J2",
        "name": "Irwin Road Crossing",
        "lat": 12.3168,
        "lon": 76.6508,
        "canvas_x": 590,
        "cross_street": "Ashoka Road",
    },
    "J3": {
        "id": "J3",
        "name": "KR Hospital Gate",
        "lat": 12.3168,
        "lon": 76.6554,
        "canvas_x": 930,
        "cross_street": "Hospital Entrance Road",
    }
}


# ============================================================================
# 1. GLOSA Speed Advisory Engine
# ============================================================================

class GLOSARequest(BaseModel):
    distance_to_next_stop_line: float = Field(..., description="Distance in meters to next junction stop bar")
    next_green_start_time: float = Field(..., description="Epoch or relative timestamp when signal switches to green")
    current_time: Optional[float] = Field(None, description="Current epoch or relative timestamp")
    time_to_green_seconds: Optional[float] = Field(None, description="Direct delta in seconds if already computed")

class GLOSAResponse(BaseModel):
    target_speed_kmh: float
    raw_calculated_speed_kmh: float
    time_to_green_seconds: float
    distance_meters: float
    advisory_message: str
    recommendation: str

def calculate_glosa_advisory(
    distance_m: float,
    next_green_time: float,
    cur_time: Optional[float] = None,
    time_to_green_direct: Optional[float] = None
) -> Dict[str, Any]:
    """
    Computes Green Light Optimal Speed Advisory (GLOSA):
    target_speed = distance_to_next_stop_line / (next_green_start_time - current_time)
    Clamped strictly between 35 km/h and 65 km/h.
    """
    now = cur_time if cur_time is not None else time.time()
    
    if time_to_green_direct is not None and time_to_green_direct > 0:
        delta_t = time_to_green_direct
    else:
        delta_t = next_green_time - now

    # Edge case: If light is already green or about to be green immediately (delta_t <= 0)
    if delta_t <= 0.2:
        raw_speed_kmh = 58.0
        delta_t = max(0.1, delta_t)
    else:
        # speed in m/s = distance_m / delta_t
        # speed in km/h = speed_m_s * 3.6
        raw_speed_kmh = (distance_m / delta_t) * 3.6

    # Strict clamping between 35 km/h and 65 km/h
    clamped_speed = max(35.0, min(65.0, raw_speed_kmh))

    # Driver advisory message
    if raw_speed_kmh > 65.0:
        recommendation = "ACCELERATE_TO_WAVE"
        msg = f"🟢 High green wave: Target {clamped_speed:.0f} km/h (Upper safe arterial limit reached)."
    elif raw_speed_kmh < 35.0:
        recommendation = "CRUISE_OR_COAST"
        msg = f"🟡 Traffic wave ahead: Cruise at {clamped_speed:.0f} km/h to hit green at stop line without stopping."
    else:
        recommendation = "MAINTAIN_GLOSA_TARGET"
        msg = f"🟢 Optimal GLOSA sync: Maintain {clamped_speed:.0f} km/h for zero-stop cascading green wave."

    return {
        "target_speed_kmh": round(clamped_speed, 1),
        "raw_calculated_speed_kmh": round(raw_speed_kmh, 1),
        "time_to_green_seconds": round(delta_t, 2),
        "distance_meters": round(distance_m, 1),
        "advisory_message": msg,
        "recommendation": recommendation
    }

@router.post("/glosa", response_model=GLOSAResponse)
async def get_glosa_advisory(req: GLOSARequest):
    """
    Calculate Green Light Optimal Speed Advisory (GLOSA) for approaching emergency vehicles.
    """
    res = calculate_glosa_advisory(
        distance_m=req.distance_to_next_stop_line,
        next_green_time=req.next_green_start_time,
        cur_time=req.current_time,
        time_to_green_direct=req.time_to_green_seconds
    )
    return GLOSAResponse(**res)


# ============================================================================
# 2. Multi-Unit Priority Arbitration Engine (J2 Irwin Road & Corridor)
# ============================================================================

class VehicleTier(int, Enum):
    TIER_1_CARDIAC_STROKE_ICU = 1
    TIER_2_FIRE_TENDER = 2
    TIER_3_POLICE_ESCORT = 3

class VehicleCandidate(BaseModel):
    vehicle_id: str
    vehicle_type: str = Field(..., description="e.g. AMBULANCE, FIRE_BRIGADE, POLICE")
    tier: Optional[int] = Field(None, description="1: Cardiac/Stroke ICU, 2: Fire Tender, 3: Police Escort")
    triage: Optional[str] = "P1"
    distance_to_j2: float = Field(..., description="Distance in meters to J2 Irwin Road intersection")
    speed_kmh: Optional[float] = 50.0
    approach_direction: str = Field("WEST", description="NORTH, SOUTH, EAST, or WEST")
    route: Optional[str] = "EASTBOUND"

class ArbitrationRequest(BaseModel):
    junction_id: str = "J2"
    vehicles: List[VehicleCandidate]
    current_time: Optional[float] = None

class ArbitrationResult(BaseModel):
    junction_id: str
    primary_vehicle_id: str
    primary_tier: int
    secondary_vehicle_id: Optional[str] = None
    secondary_tier: Optional[int] = None
    status: str
    scheduled_secondary_clearance_sec: Optional[float] = None
    arbitration_summary: str
    ordered_rankings: List[Dict[str, Any]]

def determine_vehicle_tier(vtype: str, explicit_tier: Optional[int] = None) -> int:
    """Classifies vehicle into Tier 1 (Cardiac/ICU), Tier 2 (Fire), Tier 3 (Police)."""
    if explicit_tier in (1, 2, 3):
        return explicit_tier
    vt = str(vtype).upper()
    if any(k in vt for k in ["AMB", "CARDIAC", "STROKE", "ICU", "ORGAN"]):
        return 1
    if any(k in vt for k in ["FIRE", "TENDER"]):
        return 2
    if any(k in vt for k in ["POL", "ESCORT", "INTERCEPTOR"]):
        return 3
    return 1

def arbitrate_multi_vehicle(
    vehicles: List[VehicleCandidate],
    junction_id: str = "J2",
    cur_time: Optional[float] = None
) -> Dict[str, Any]:
    """
    Arbitrates multi-vehicle conflicting arrivals at J2 Irwin Road crossing:
    Tier 1 (Cardiac/Stroke ICU, score 30,000) > Tier 2 (Fire Tender, score 20,000) > Tier 3 (Police, score 10,000).
    Grants immediate preemption to highest priority and schedules clearance for the secondary unit.
    """
    if not vehicles:
        raise ValueError("No vehicle candidates provided for arbitration.")

    scored_vehicles = []
    for v in vehicles:
        tier = determine_vehicle_tier(v.vehicle_type, v.tier)
        # Tier 1 -> 30000 base, Tier 2 -> 20000 base, Tier 3 -> 10000 base
        tier_base = (4 - tier) * 10000
        # Triage bonus for P1
        triage_bonus = 2000 if str(v.triage).upper() == "P1" else 0
        # Proximity bonus (closer vehicle gets small tie-breaker bonus)
        proximity_bonus = max(0.0, 1000.0 - min(1000.0, v.distance_to_j2))

        total_score = tier_base + triage_bonus + proximity_bonus

        scored_vehicles.append({
            "vehicle_id": v.vehicle_id,
            "vehicle_type": v.vehicle_type,
            "tier": tier,
            "triage": v.triage,
            "distance": v.distance_to_j2,
            "speed_kmh": v.speed_kmh or 50.0,
            "approach_direction": v.approach_direction,
            "route": v.route,
            "priority_score": total_score
        })

    # Sort descending by priority score
    scored_vehicles.sort(key=lambda x: x["priority_score"], reverse=True)

    winner = scored_vehicles[0]
    secondary = scored_vehicles[1] if len(scored_vehicles) > 1 else None

    # Calculate clearance schedule for secondary vehicle
    scheduled_clearance_sec = None
    if secondary:
        winner_speed_ms = max(5.0, (winner["speed_kmh"] * 1000.0) / 3600.0)
        # Time for winner to reach and clear J2 junction box (68m intersection box + 20m buffer)
        winner_eta = (winner["distance"] + 88.0) / winner_speed_ms
        safety_yellow_buffer = 3.0
        scheduled_clearance_sec = round(winner_eta + safety_yellow_buffer, 1)

    summary = (
        f"🏆 ARBITRATION RESOLVED at {junction_id} (Irwin Road Crossing): "
        f"Preemption GRANTED to {winner['vehicle_id']} (Tier {winner['tier']} - {winner['vehicle_type']}). "
    )
    if secondary:
        summary += (
            f"Secondary unit {secondary['vehicle_id']} (Tier {secondary['tier']} - {secondary['vehicle_type']}) "
            f"held at upstream safety line. Immediate clearance SCHEDULED in {scheduled_clearance_sec}s."
        )
    else:
        summary += "Single priority unit corridor locked."

    return {
        "junction_id": junction_id,
        "primary_vehicle_id": winner["vehicle_id"],
        "primary_tier": winner["tier"],
        "secondary_vehicle_id": secondary["vehicle_id"] if secondary else None,
        "secondary_tier": secondary["tier"] if secondary else None,
        "status": "ARBITRATION_ENGAGED",
        "scheduled_secondary_clearance_sec": scheduled_clearance_sec,
        "arbitration_summary": summary,
        "ordered_rankings": scored_vehicles
    }

@router.post("/arbitrate", response_model=ArbitrationResult)
async def arbitrate_crossing(req: ArbitrationRequest):
    """
    Arbitrates multi-vehicle conflicting arrivals at J2 Irwin Road Crossing or arterial junctions.
    """
    try:
        res = arbitrate_multi_vehicle(req.vehicles, req.junction_id, req.current_time)
        return ArbitrationResult(**res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# 3. Post-Preemption Queue Flush Engine
# ============================================================================

class QueueFlushRequest(BaseModel):
    junction_id: str = "J2"
    cctv_queues: Dict[str, int] = Field(..., description="CCTV Queue counts for N, S, E, W approaches")
    ev_corridor_axis: Optional[str] = Field("EW", description="Axis of emergency corridor: EW (East-West) or NS")
    ev_departed_direction: Optional[str] = "WEST"

class QueueFlushResponse(BaseModel):
    junction_id: str
    flush_direction: str
    flush_approach_name: str
    extended_green_seconds: float
    max_cctv_queue_detected: int
    queue_counts_snapshot: Dict[str, int]
    reason: str
    return_to_normal_after_sec: float

def calculate_queue_flush(
    cctv_queues: Dict[str, int],
    junction_id: str = "J2",
    ev_axis: str = "EW"
) -> Dict[str, Any]:
    """
    Reads CCTV camera queue counters (N, S, E, W).
    When an emergency vehicle leaves an intersection (post-preemption),
    dynamically calculates an extended green flush time for the longest-waiting cross-street
    before returning to standard fixed-time cycles.
    """
    # Cross street approaches for East-West corridor (Irwin Road) are North and South
    if ev_axis.upper() in ["EW", "EAST_WEST"]:
        cross_candidates = {k.upper(): cctv_queues.get(k, 0) for k in ["N", "S"]}
    elif ev_axis.upper() in ["NS", "NORTH_SOUTH"]:
        cross_candidates = {k.upper(): cctv_queues.get(k, 0) for k in ["E", "W"]}
    else:
        cross_candidates = {k.upper(): v for k, v in cctv_queues.items()}

    # Select the cross-street approach with highest waiting queue
    sorted_queues = sorted(cross_candidates.items(), key=lambda x: x[1], reverse=True)
    best_dir, max_queue = sorted_queues[0] if sorted_queues else ("N", 0)

    # Dynamic Green Time Formula:
    # Base starting green = 12.0s
    # Each waiting vehicle detected by AI CCTV adds 1.25s (average discharge headway)
    # Clamped between 14.0s minimum and 28.0s maximum
    calculated_green = 12.0 + (max_queue * 1.25)
    flush_green_time = round(max(14.0, min(28.0, calculated_green)), 1)

    approach_names = {
        "N": "North Approach (Ashoka Road Southbound / Sayyaji Rao)",
        "S": "South Approach (Ashoka Road Northbound / City Market)",
        "E": "East Approach (Irwin Road Westbound)",
        "W": "West Approach (Irwin Road Eastbound)"
    }

    reason = (
        f"Post-preemption dynamic flush: Cross-approach {best_dir} has highest queue "
        f"({max_queue} vehicles detected by AI CCTV). Granted extended green of {flush_green_time}s "
        f"to clear backlog before restoring standard cyclic timing."
    )

    return {
        "junction_id": junction_id,
        "flush_direction": best_dir,
        "flush_approach_name": approach_names.get(best_dir, best_dir),
        "extended_green_seconds": flush_green_time,
        "max_cctv_queue_detected": max_queue,
        "queue_counts_snapshot": cctv_queues,
        "reason": reason,
        "return_to_normal_after_sec": flush_green_time + 3.0  # including yellow buffer
    }

@router.post("/flush", response_model=QueueFlushResponse)
async def trigger_post_preemption_flush(req: QueueFlushRequest):
    """
    Read CCTV queue counters and compute dynamic extended green flush time for starved cross-arterials.
    """
    res = calculate_queue_flush(
        cctv_queues=req.cctv_queues,
        junction_id=req.junction_id,
        ev_axis=req.ev_corridor_axis or "EW"
    )
    return QueueFlushResponse(**res)


# ============================================================================
# 4. Corridor Status & Diagnostic Endpoint
# ============================================================================

@router.get("/status")
async def get_corridor_status():
    """
    Returns real-time corridor overview including all 3 Mysuru arterial junctions
    (J1 Ayurveda Hospital, J2 Irwin Road, J3 KR Hospital) and current preemption status.
    """
    return {
        "corridor_name": "Mysuru Irwin Road Green Corridor",
        "total_arterial_length_meters": 1150.0,
        "junctions": CORRIDOR_JUNCTIONS,
        "glosa_clamping": {"min_kmh": 35.0, "max_kmh": 65.0},
        "priority_tiers": {
            "Tier 1": "Cardiac/Stroke ICU (Base Score: 30,000)",
            "Tier 2": "Fire Tender & Rescue (Base Score: 20,000)",
            "Tier 3": "Police Escort / Interceptor (Base Score: 10,000)"
        },
        "flush_policy": "AI CCTV queue-proportional dynamic green extension (14s-28s)",
        "timestamp": time.time()
    }
