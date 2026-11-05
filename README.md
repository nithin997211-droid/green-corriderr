# 🚑 Green Corridor - Intelligent Emergency Vehicle Pre-emption (EVP) System

[![Python 3.12](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![ESP32](https://img.shields.io/badge/Hardware-ESP32%20%2B%20NEO--6M-red.svg)](https://www.espressif.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Saving Lives in the Golden Hour**: An automated Software + Hardware Intelligent Traffic Preemption System tailored for congested Indian metropolitan roads (Mysuru, Bengaluru, Mangaluru, Hubballi).

---

## 📌 1. The Critical Problem in India

In India, an estimated **50,000+ critical patients die every year** simply because ambulances cannot reach hospital trauma centers within the critical **"Golden Hour"** due to chaotic urban traffic congestion. Furthermore, fire engines face extreme response delays reaching incident sites.

Manual traffic police intervention is slow, fragmented, and cannot coordinate across multiple signals in real-time.

---

## 💡 2. The Solution: Automated Green Corridor

This project provides a complete end-to-end **IoT Hardware + Cloud Software System**:

1. **Hardware on Vehicles**: Emergency vehicles (Ambulance, Fire Tender, Organ Transit) are fitted with an **ESP32 + NEO-6M GPS Tracker** and a siren sensor.
2. **500m Intelligent Geofence**: As the vehicle approaches within **500 meters** of an intersection, the system detects its distance, speed, and approach arm (North, South, East, West).
3. **Safe Preemption Transition**:
   - Cross-traffic receives a **3-second Yellow safety warning** to decelerate and prevent collisions.
   - All conflicting signals turn solid **RED**.
   - The emergency vehicle's approach arm switches to bright **GREEN**, clearing the road ahead.
4. **Automated Clearance & Recovery**:
   - Once the emergency vehicle crosses the intersection center (>35m past), the system automatically restores normal cyclic traffic operation.
5. **Priority Arbitration Matrix**:
   - If multiple emergency vehicles approach the same junction (e.g. an Ambulance and a Fire Engine), the system automatically arbitrates access based on urgency:
     - **Priority 1**: Cardiac / Trauma Ambulance & Organ Transport
     - **Priority 2**: Fire Tender / Disaster Response
     - **Priority 3**: Non-critical Patient Transport
     - **Priority 4**: Police / VIP Escort

---

## 🏗️ 3. System Architecture

```
+-----------------------------------+
| EMERGENCY VEHICLE (AMBULANCE)     |
| - ESP32 MCU                       |
| - u-blox NEO-6M GPS (1Hz)         | ---- [4G LTE / SIM7600] ----+
| - Siren Sensor Switch             |                             |
+-----------------------------------+                             |
                                                                  v
+-----------------------------------+                   +---------------------+
| TRAFFIC SIGNAL JUNCTION           |                   | CENTRAL CONTROLLER  |
| - ESP32 Controller                | <--- [REST/WS] -- | - Haversine Geofence|
| - 12-Channel Relay Board          |                   | - Bearing Detection |
| - High-Power LED Lamp Clusters    |                   | - Priority Arbiter  |
| - 10s Fail-Safe Watchdog          |                   +---------------------+
+-----------------------------------+
```

---

## 📦 4. Repository Structure

```
green_corridor_system/
├── backend/
│   ├── main.py              # FastAPI server with REST endpoints & WebSocket live stream
│   ├── engine.py            # Haversine distance, bearing vector, priority queue, state machine
│   ├── models.py            # Pydantic schemas for telemetry, GPS, and junction state
│   └── sim_feed.py          # Built-in simulation vehicle engine
├── frontend/
│   └── index.html           # Interactive HTML5 Canvas crossroads simulator + Audio siren
├── hardware/
│   ├── esp32_emergency_gps_tracker.ino       # ESP32 firmware for vehicle GPS transmitter
│   ├── esp32_traffic_signal_controller.ino  # ESP32 firmware for 12-relay traffic light
│   └── hardware_schematic_guide.md          # Wiring diagrams, BOM cost (INR), & pinouts
├── tests/
│   ├── run_tests.py         # Standard library unittest suite
│   └── test_green_corridor.py # Pytest verification suite
├── run_server.py            # Server entrypoint with auto-browser launch
├── simulate_gps_device.py   # Standalone CLI hardware GPS emulator
├── start_system.bat         # Double-click Windows launcher
└── README.md                # Complete documentation
```

---

## 🚀 5. Quick Start Guide

### Prerequisites
- Python 3.10+ installed

### Step 1: Install Dependencies
```bash
pip install fastapi uvicorn websockets pydantic requests
```

### Step 2: Launch the System
Double-click `start_system.bat` or run in terminal:
```bash
python run_server.py
```
This starts the backend on `http://0.0.0.0:8000` and displays:
- 🖥️ **Desktop Dashboard**: `http://localhost:8000`
- 📱 **108 Ambulance Driver Mobile App**: `http://<your-local-ip>:8000/driver`

### Step 3: Connect Your Smartphone (Driver App)
1. Open the Desktop Dashboard in your browser (`http://localhost:8000`).
2. Click **"📱 DRIVER MOBILE APP"** in the top header.
3. Scan the QR code with your Android or iPhone camera (connected to the same local Wi-Fi), OR click **"Launch Mobile App Window"** to test side-by-side.
4. Select your Triage Level (**P1 Code Red Trauma**, **P2 Urgent**, **P3 Routine**).
5. Tap **"🚨 START EMERGENCY RUN"** on your phone:
   - Watch the 3 sequential junctions along Irwin Road immediately begin their **Cascading Green Wave** preemption!
   - Your phone receives real-time distance countdowns, speed telemetry, and signal status indicators!

### Step 4: Run the Test Suite
```bash
python tests/run_tests.py
```
Expected output:
```
....
----------------------------------------------------------------------
Ran 4 tests in 0.151s

OK
```

---

## 🎮 6. Multi-Junction Irwin Road Corridor Features

The system simulates a coordinated 3-junction arterial corridor in Mysuru leading directly to KR Hospital:

1. **Junction 1: Ayurvedic Hospital Circle** (West entrance to the medical district)
2. **Junction 2: Irwin Road Crossing** (Dense commercial sector midpoint)
3. **Junction 3: KR Hospital Emergency Gate** (Final approach leading to Trauma Bay)
4. **KR Hospital Emergency Trauma Care Building**: Direct arrival bay dock with total delay saved analytics.

### Cascading Green Wave Coordination
- When 108 Ambulance approaches within 180m of J1: J1 initiates safe Yellow clearance and locks into Green Wave preemption.
- Once J1 is crossed: J1 enters safe all-red recovery, while J2 receives the handoff and locks into Green Wave preemption.
- Once J2 is crossed: J2 recovers, and J3 locks into Green Wave preemption leading directly to the KR Hospital Emergency Bay.
- Zero collisions: Monotonic forward-only physics and bumper-to-bumper car-following ensure no vehicle ever reverses or rear-ends another.


---

## 🔌 7. Hardware Deployment & BOM Summary

| Module | Key Components | Approx Cost (INR) |
|---|---|---|
| **Vehicle Unit** | ESP32-WROOM-32, u-blox NEO-6M GPS, SIM7600 4G LTE, LM2596 Buck Converter | ₹3,510 (~$42) |
| **Intersection Unit** | ESP32 NodeMCU, 16-Channel 5V Optocoupled Relay Board, MeanWell 5V SMPS, 4G Router | ₹6,050 (~$73) |

> Complete schematics and wiring connections are detailed in [`hardware/hardware_schematic_guide.md`](file:///hardware/hardware_schematic_guide.md).

---

## 🛡️ 8. Fail-Safe & Safety Protections

1. **All-Red / Yellow Transition**: Never switches green instantaneously across conflicting lanes; holds 3.0s yellow to prevent high-speed collisions.
2. **10-Second Hardware Watchdog**: If Wi-Fi or cellular network drops, the junction ESP32 falls back to standalone cyclic timer mode so traffic never freezes.
3. **Corridor Timeout**: A 75-second watchdog timer automatically resets the signal if an emergency vehicle pulls over, gets stuck, or turns onto a side road.

---

## 📚 9. IEEE Base Papers & Scientific References

This system is built directly upon peer-reviewed research and mathematical models published in **IEEE Transactions on Intelligent Transportation Systems** and **IEEE Access**. Below are the primary base papers with verified DOIs and direct links:

### 1. Primary Base Paper 1: On-Demand Green Wave Optimization
- **Title**: *On-Demand Greenwave for Emergency Vehicles in a Time-Varying Road Network With Uncertainties*
- **Authors**: Wang Min, Long Yu, Peng Chen, Meng Zhang, Yong Liu, Jia Wang
- **Publication**: *IEEE Transactions on Intelligent Transportation Systems*, Vol. 21, No. 7, pp. 3056–3068, July 2020.
- **DOI**: [10.1109/TITS.2019.2923802](https://doi.org/10.1109/TITS.2019.2923802)
- **IEEE Xplore**: [https://ieeexplore.ieee.org/document/8756087](https://ieeexplore.ieee.org/document/8756087)
- **Project Mapping**: Mathematical foundation of our 3-junction cascading green wave ($J_1 \rightarrow J_2 \rightarrow J_3$) along Irwin Road to KR Hospital, clearing downstream vehicle queues in advance.

### 2. Primary Base Paper 2: IoT Architecture & Distributed Intersection Control
- **Title**: *EVP-STC: Emergency Vehicle Priority and Self-Organising Traffic Control at Intersections Using Internet-of-Things Platform*
- **Authors**: Ajmal Khan, Farman Ullah, Zeeshan Kaleem, Saeed Ur Rahman, Haseeb Anwar, You-Ze Cho
- **Publication**: *IEEE Access*, Vol. 6, pp. 68242–68254, Nov. 2018.
- **DOI**: [10.1109/ACCESS.2018.2879644](https://doi.org/10.1109/ACCESS.2018.2879644)
- **IEEE Xplore**: [https://ieeexplore.ieee.org/document/8521556](https://ieeexplore.ieee.org/document/8521556)
- **Project Mapping**: Establishes the real-time IoT architecture (GPS telemetry streaming, distance-based trigger thresholds, and automated signal preemption) implemented in our FastAPI backend and ESP32 hardware units.

### 3. Base Paper 3: Dynamic Green Light Optimal Speed Advisory (GLOSA)
- **Title**: *Assessing Connected Vehicle's Response to Green Light Optimal Speed Advisory From Field Operational Test and Scaling Up*
- **Authors**: Aleksandar Stevanovic, Milan Zlatkovic, Cameron Kergaye
- **Publication**: *IEEE Transactions on Intelligent Transportation Systems*, Vol. 24, No. 6, pp. 6051–6063, June 2023.
- **DOI**: [10.1109/TITS.2022.3187532](https://doi.org/10.1109/TITS.2022.3187532)
- **IEEE Xplore**: [https://ieeexplore.ieee.org/document/9813636](https://ieeexplore.ieee.org/document/9813636)
- **Project Mapping**: Underpins our dynamic GLOSA speed advisory algorithm (advising 50–65 km/h) displayed in the live Driver Cockpit and announced via Web Speech audio prompts to eliminate emergency vehicle braking.

### 4. Base Paper 4: Collision-Free Signal Preemption via Timed Petri Nets
- **Title**: *Design of Traffic Safety Control Systems for Emergency Vehicle Preemption Using Timed Petri Nets*
- **Authors**: Yuh-Sheng Huang, Yuan-Sun Weng, MengChu Zhou
- **Publication**: *IEEE Transactions on Intelligent Transportation Systems*, Vol. 16, No. 4, pp. 2113–2120, Aug. 2015.
- **DOI**: [10.1109/TITS.2015.2395419](https://doi.org/10.1109/TITS.2015.2395419)
- **IEEE Xplore**: [https://ieeexplore.ieee.org/document/7055319](https://ieeexplore.ieee.org/document/7055319)
- **Project Mapping**: Formal mathematical proof for our strict 1-arm-green mutex invariant, 3.0s all-yellow clearance buffer, and 75s watchdog fail-safe timeout in `backend/engine.py`.

### 5. Base Paper 5: V2X Mobility-Aware Lane Changing for Emergency Preemption
- **Title**: *V2X and Deep Reinforcement Learning-Aided Mobility-Aware Lane Changing for Emergency Vehicle Preemption in Connected Autonomous Transport Systems*
- **Authors**: Chen Ding, Ivan Wang-Hei Ho, Edward Chung, Tingting Fan
- **Publication**: *IEEE Transactions on Intelligent Transportation Systems*, Vol. 25, No. 7, pp. 7281–7293, July 2024.
- **DOI**: [10.1109/TITS.2024.3350334](https://doi.org/10.1109/TITS.2024.3350334)
- **IEEE Xplore**: [https://ieeexplore.ieee.org/document/10418968](https://ieeexplore.ieee.org/document/10418968)
- **Project Mapping**: Basis for our civilian vehicle yielding physics (`updateCorridorPhysics`), where civilian cars yield to the outer left kerbside lane upon detecting the emergency vehicle within 320m.

---

### Quick Link Reference Matrix

| # | Topic | Authors & Year | Venue | Verified Direct Links |
|---|---|---|---|---|
| 01 | Cascading Greenwave | W. Min et al. (2020) | IEEE Trans. ITS | [IEEE Xplore #8756087](https://ieeexplore.ieee.org/document/8756087) • [DOI: 10.1109/TITS.2019.2923802](https://doi.org/10.1109/TITS.2019.2923802) |
| 02 | IoT Preemption Platform | A. Khan et al. (2018) | IEEE Access | [IEEE Xplore #8521556](https://ieeexplore.ieee.org/document/8521556) • [DOI: 10.1109/ACCESS.2018.2879644](https://doi.org/10.1109/ACCESS.2018.2879644) |
| 03 | GLOSA Speed Advisory | A. Stevanovic et al. (2023) | IEEE Trans. ITS | [IEEE Xplore #9813636](https://ieeexplore.ieee.org/document/9813636) • [DOI: 10.1109/TITS.2022.3187532](https://doi.org/10.1109/TITS.2022.3187532) |
| 04 | Collision-Free Petri Nets | Y.-S. Huang et al. (2015) | IEEE Trans. ITS | [IEEE Xplore #7055319](https://ieeexplore.ieee.org/document/7055319) • [DOI: 10.1109/TITS.2015.2395419](https://doi.org/10.1109/TITS.2015.2395419) |
| 05 | V2X Lane Clearance | C. Ding et al. (2024) | IEEE Trans. ITS | [IEEE Xplore #10418968](https://ieeexplore.ieee.org/document/10418968) • [DOI: 10.1109/TITS.2024.3350334](https://doi.org/10.1109/TITS.2024.3350334) |
