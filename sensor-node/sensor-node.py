import os
import time
import uuid
from pathlib import Path

from arduino_data import WaterMonitor
from daphnia_monitor import CameraUnavailableError, DaphniaMonitor
from lora_radio import cleanup_lora_resources, init_lora_radio
from sim7600_gps import open_sim7600_serial, power_on_gps, read_gps_payload, close_sim7600_serial

rfm9x = None
lora_cs = None
lora_reset = None
lora_spi = None


def _sanitize_machine_id(raw_value):
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    cleaned = "".join(ch for ch in raw_value.strip() if ch in allowed)
    return cleaned or "unknown-node"


def get_machine_id():
    env_machine_id = os.getenv("SENSOR_MACHINE_ID") or os.getenv("MACHINE_ID")
    if env_machine_id:
        return _sanitize_machine_id(env_machine_id)

    try:
        with open("/etc/machine-id", "r", encoding="utf-8") as machine_id_file:
            machine_id = machine_id_file.readline().strip()
            if machine_id:
                return _sanitize_machine_id(machine_id)
    except OSError:
        pass

    machine_id_path = Path(
        os.getenv("SENSOR_MACHINE_ID_FILE", str(Path(__file__).resolve().parent / ".machine_id"))
    )
    try:
        if machine_id_path.exists():
            existing_id = machine_id_path.read_text(encoding="utf-8").strip()
            if existing_id:
                return _sanitize_machine_id(existing_id)
    except OSError:
        pass

    generated_id = _sanitize_machine_id(uuid.uuid4().hex)
    try:
        machine_id_path.parent.mkdir(parents=True, exist_ok=True)
        machine_id_path.write_text(generated_id + "\n", encoding="utf-8")
    except OSError as error:
        print(f"Warning: could not persist generated machine ID: {error}")
    return generated_id

try:
    rfm9x, lora_cs, lora_reset, lora_spi = init_lora_radio()
except Exception:
    exit()

# --- 2. SIM7600 Serial Setup ---
sim_serial = None

try:
    sim_serial = open_sim7600_serial()
except Exception as e:
    print("Serial Error. Did you enable the Serial port in raspi-config?", e)
    exit()


def setup_daphnia_monitor():
    if os.getenv("ENABLE_DAPHNIA", "1") != "1":
        print("Daphnia monitor disabled (ENABLE_DAPHNIA != 1).")
        return None, None

    camera_index = int(os.getenv("DAPHNIA_CAMERA_INDEX", "0"))
    try:
        cap = DaphniaMonitor.open_camera(camera_index)
        monitor = DaphniaMonitor()
        print(f"Daphnia monitor enabled on camera index {camera_index}.")
        return monitor, cap
    except CameraUnavailableError as error:
        print(f"Daphnia monitor unavailable: {error}")
        return None, None


def setup_water_monitor():
    if os.getenv("ENABLE_WATER", "1") != "1":
        print("Water monitor disabled (ENABLE_WATER != 1).")
        return None

    port = os.getenv("ARDUINO_PORT", "/dev/ttyUSB0")
    baud_rate = int(os.getenv("ARDUINO_BAUD", "9600"))
    try:
        monitor = WaterMonitor(port=port, baud_rate=baud_rate)
        print(f"Water monitor enabled on {port} @ {baud_rate} baud.")
        return monitor
    except Exception as error:
        print(f"Water monitor unavailable: {error}")
        return None


def to_water_payload(reading):
    if not isinstance(reading, dict):
        return "WATER:ERR"

    temperature = reading.get("temperature")
    conductivity = reading.get("conductivity")
    ph = reading.get("ph")
    if conductivity is not None and ph is not None:
        temp_value = float(temperature) if temperature is not None else 0.0
        return f"WATER:T{temp_value:.2f},C{float(conductivity):.2f},P{float(ph):.2f}"

    if reading.get("error"):
        return "WATER:ERR"

    return "WATER:NA"


# --- 3. Initialize GPS ---
print("Powering on GPS...")
power_on_gps(sim_serial)

monitor, cap = setup_daphnia_monitor()
water_monitor = setup_water_monitor()
machine_id = get_machine_id()
print(f"Machine ID: {machine_id}")
print("Starting transmission loop...")

# --- 4. Main Loop ---
try:
    while True:
        gps_payload = read_gps_payload(sim_serial)

        daphnia_payload = "DAPH:NA"
        if monitor is not None and cap is not None:
            try:
                window_seconds = float(os.getenv("DAPHNIA_WINDOW_SECONDS", "8"))
                fps = float(os.getenv("DAPHNIA_FPS", "10"))
                frames = DaphniaMonitor.capture_window(cap, duration_s=window_seconds, fps_target=fps)
                if len(frames) >= 2:
                    metrics = monitor.analyze_frames(frames, fps=fps)
                    daphnia_payload = DaphniaMonitor.to_payload(metrics)
                else:
                    daphnia_payload = "DAPH:ERR,NOFRAMES"
            except Exception as error:  # Keep telemetry running even if camera analysis fails.
                daphnia_payload = "DAPH:ERR"
                print(f"Daphnia monitor error: {error}")

        water_payload = "WATER:NA"
        if water_monitor is not None:
            try:
                water_payload = to_water_payload(water_monitor.get_reading())
            except Exception as error:  # Keep telemetry running even if serial read fails.
                water_payload = "WATER:ERR"
                print(f"Water monitor error: {error}")

        payload = f"MID:{machine_id}|{gps_payload}|{daphnia_payload}|{water_payload}"

        if rfm9x is not None:
            print(f"Transmitting over LoRa: {payload}")
            rfm9x.send(bytes(payload, "utf-8"))
        else:
            print(f"LoRa send skipped (disabled): {payload}")

        print("-" * 30)
        time.sleep(5)
except KeyboardInterrupt:
    print("Stopping sensor node (Ctrl+C).")
finally:
    if cap is not None:
        cap.release()
    if water_monitor is not None:
        water_monitor.close()
    close_sim7600_serial(sim_serial)
    cleanup_lora_resources(lora_cs, lora_reset, lora_spi)
