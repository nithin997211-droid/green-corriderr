# Green Corridor Hardware Architecture & Wiring Guide

This guide provides the complete hardware specification, circuit schematics, Bill of Materials (BOM), and assembly instructions for deploying the **Green Corridor Intelligent Emergency Vehicle Preemption System**.

---

## 1. System Architecture Diagram

```
+-----------------------------------+          4G LTE / GSM / Wi-Fi
| Emergency Vehicle (Ambulance/Fire)| ------------------------------------+
|  - ESP32 Microcontroller          |                                     |
|  - u-blox NEO-6M GPS Module       |                                     v
|  - Siren Relay / Dashboard Switch |                          +----------------------+
+-----------------------------------+                          | Central Cloud/Server |
                                                               | (FastAPI Engine)     |
+-----------------------------------+                          +----------------------+
| Traffic Signal Intersection       |                                     |
|  - ESP32 Signal Controller        | <-----------------------------------+
|  - 12-Channel Isolated Relay Board|      REST API / WebSockets / MQTT
|  - Red / Yellow / Green Lamps     |
|  - Siren Alarm Buzzer             |
+-----------------------------------+
```

---

## 2. Bill of Materials (BOM)

### A. Vehicle Tracker Unit (Per Emergency Vehicle)
| Component | Specification | Estimated Cost (INR) | Estimated Cost (USD) |
|---|---|---|---|
| **ESP32-WROOM-32** | Wi-Fi + Bluetooth Dual-Core MCU | ₹450 | $5.50 |
| **u-blox NEO-6M GPS** | Ceramic patch antenna, 9600 baud, UART | ₹400 | $4.80 |
| **SIM7600E-H (or SIM800L)** | 4G LTE High-speed GSM/GPRS Modem | ₹2,200 | $26.50 |
| **LM2596 DC-DC Buck Converter** | 12V/24V Vehicle Battery to 5V 3A | ₹120 | $1.50 |
| **Automotive Fuse + Fuse Holder** | 2A Fast-blow Inline Fuse | ₹40 | $0.50 |
| **Toggle Switch / Relay Sensor** | Detects when emergency siren/strobe is ON | ₹50 | $0.60 |
| **IP65 Enclosure Box** | Waterproof automotive enclosure | ₹250 | $3.00 |
| **Total per Vehicle** | | **~₹3,510** | **~$42.40** |

### B. Traffic Intersection Controller Unit (Per Signal Junction)
| Component | Specification | Estimated Cost (INR) | Estimated Cost (USD) |
|---|---|---|---|
| **ESP32 NodeMCU Development Board** | 30-pin Dual-Core ESP32 | ₹450 | $5.50 |
| **16-Channel 5V Relay Board** | Optocoupled 10A 250VAC Relays | ₹750 | $9.00 |
| **Industrial 12V/5V Power Supply** | Mean Well 5V 4A SMPS (DIN Rail) | ₹850 | $10.20 |
| **High Decibel 12V Piezo Siren** | Audio strobe for intersection alert | ₹300 | $3.60 |
| **4G Industrial Wi-Fi Router / SIM** | Cellular link with external antenna | ₹2,500 | $30.00 |
| **Metal Weatherproof Enclosure** | IP66 Cabinet for traffic control post | ₹1,200 | $14.50 |
| **Total per Intersection** | | **~₹6,050** | **~$72.80** |

---

## 3. Circuit Schematics & Pin Connections

### A. Vehicle GPS Tracker Wiring
```
[Vehicle 12V Battery] ---> [2A Inline Fuse] ---> [LM2596 IN+] 
                                                [LM2596 OUT+] ---> ESP32 5V (VIN)
                                                [LM2596 GND]  ---> ESP32 GND

NEO-6M GPS Module:
- VCC  ---> ESP32 3.3V
- GND  ---> ESP32 GND
- TX   ---> ESP32 GPIO 16 (RX2)
- RX   ---> ESP32 GPIO 17 (TX2)

Emergency Siren Detect:
- Siren Switch / Relay NO  ---> ESP32 GPIO 4
- Siren Switch Common     ---> ESP32 GND (Internal Pull-Up enabled)

Status LED:
- GPIO 2 ---> Onboard Blue LED (Blinks on HTTP transmission)
```

### B. Intersection Signal Controller Wiring
```
ESP32 Pin Allocation to 12-Channel Relay Board:

NORTH ARM:
- GPIO 13 ---> Relay IN 1 (North Red Lamp)
- GPIO 12 ---> Relay IN 2 (North Yellow Lamp)
- GPIO 14 ---> Relay IN 3 (North Green Lamp)

EAST ARM:
- GPIO 27 ---> Relay IN 4 (East Red Lamp)
- GPIO 26 ---> Relay IN 5 (East Yellow Lamp)
- GPIO 25 ---> Relay IN 6 (East Green Lamp)

SOUTH ARM:
- GPIO 33 ---> Relay IN 7 (South Red Lamp)
- GPIO 32 ---> Relay IN 8 (South Yellow Lamp)
- GPIO 15 ---> Relay IN 9 (South Green Lamp)

WEST ARM:
- GPIO 19 ---> Relay IN 10 (West Red Lamp)
- GPIO 18 ---> Relay IN 11 (West Yellow Lamp)
- GPIO 5  ---> Relay IN 12 (West Green Lamp)

AUDIO ALERT:
- GPIO 4  ---> Relay IN 13 (Pedestrian Warning Siren)
```

---

## 4. Safety Fail-Safe Architecture

1. **Optical Isolation**: All 230V AC or 24V DC traffic lamp power lines are isolated from the ESP32 microcontrollers using optocouplers on the relay boards.
2. **Hardware Watchdog Timer**: If the cellular or Wi-Fi network experiences an outage longer than 10 seconds, the junction ESP32 firmware enters `runAutonomousFailsafeCycle()`, maintaining normal round-robin traffic lights so Indian roads never face gridlock.
3. **Smooth Yellow Transition**: When an ambulance approaches, all non-priority directions first transition to **YELLOW** for 3.0 seconds to give moving vehicles safe stopping distance before turning solid **RED**.
4. **Timeout Watchdog**: The green corridor automatically resets after a maximum of 75 seconds if a vehicle stops or changes route.
