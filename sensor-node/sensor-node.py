import os
import time

import serial
import board
import busio
import digitalio
import adafruit_rfm9x

from daphnia_monitor import CameraUnavailableError, DaphniaMonitor

# --- 1. LoRa Setup ---
RADIO_FREQ_MHZ = 433.0
CS = digitalio.DigitalInOut(board.D5)  # Using GPIO 5 as configured previously
RESET = digitalio.DigitalInOut(board.D22)
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
rfm9x = None

try:
    rfm9x = adafruit_rfm9x.RFM9x(spi, CS, RESET, RADIO_FREQ_MHZ)
    rfm9x.tx_power = 13
    print("LoRa module initialized.")
except RuntimeError as error:
    print("LoRa Error:", error)
    exit()

if rfm9x is None:
    print("LoRa radio was not initialized.")
    exit()

assert rfm9x is not None

# --- 2. SIM7600 Serial Setup ---
# /dev/serial0 is the default hardware serial port on the Pi (Pins 8 & 10)
SERIAL_PORT = '/dev/serial0'
BAUD_RATE = 115200

try:
    sim_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print("SIM7600 Serial port opened.")
except Exception as e:
    print("Serial Error. Did you enable the Serial port in raspi-config?", e)
    exit()


def send_at_command(command, wait_time=1):
    """Sends an AT command to the SIM7600 and returns the response."""
    sim_serial.write((command + '\r\n').encode())
    time.sleep(wait_time)
    response = ""
    while sim_serial.in_waiting:
        response += sim_serial.read(sim_serial.in_waiting).decode('utf-8', errors='ignore')
    return response


def extract_gps_payload(gps_data):
    payload = "Waiting for GPS fix..."
    lines = gps_data.split('\n')

    for line in lines:
        if "+CGPSINFO:" in line:
            clean_line = line.strip()
            if ",,,,,,,," in clean_line:
                print("No GPS fix. Ensure the GPS antenna is outside with a clear view of the sky.")
            else:
                payload = clean_line
                print("GPS fix acquired!")
            break

    return payload


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


# --- 3. Initialize GPS ---
print("Powering on GPS...")
# AT+CGPS=1 turns on the GNSS engine
send_at_command("AT+CGPS=1", 2)

monitor, cap = setup_daphnia_monitor()
print("Starting transmission loop...")

# --- 4. Main Loop ---
while True:
    gps_data = send_at_command("AT+CGPSINFO", 1)
    gps_payload = extract_gps_payload(gps_data)

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

    payload = f"{gps_payload}|{daphnia_payload}"

    print(f"Transmitting over LoRa: {payload}")
    rfm9x.send(bytes(payload, "utf-8"))

    print("-" * 30)
    time.sleep(5)
