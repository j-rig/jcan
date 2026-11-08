PID_MONITOR_STATUS = 0x01

# Spark-ignition (gasoline) monitor layout only — out of scope: compression-ignition (diesel),
# none of this tool's 3 target vehicles are diesel.
CONTINUOUS_MONITORS = ["misfire", "fuel_system", "components"]

NONCONTINUOUS_MONITORS = [
    "catalyst",
    "heated_catalyst",
    "evaporative_system",
    "secondary_air_system",
    "ac_refrigerant",
    "oxygen_sensor",
    "oxygen_sensor_heater",
    "egr_system",
]


def decode_readiness(data: bytes) -> dict:
    a, b, c, d = data[0], data[1], data[2], data[3]
    monitors = []
    for i, name in enumerate(CONTINUOUS_MONITORS):
        if b & (1 << i):
            monitors.append({"name": name, "ready": not bool(b & (1 << (i + 4)))})
    for i, name in enumerate(NONCONTINUOUS_MONITORS):
        if c & (1 << i):
            monitors.append({"name": name, "ready": not bool(d & (1 << i))})
    return {
        "mil_on": bool(a & 0x80),
        "dtc_count": a & 0x7F,
        "monitors": monitors,
    }
