import os
from pathlib import Path
from urllib.parse import quote, urlparse

import adafruit_rfm9x
import board
import busio
import digitalio
import requests


RADIO_FREQ_MHZ = float(os.getenv("LORA_RADIO_FREQ_MHZ", "433.0"))


def parse_dotenv_api_address(dotenv_path):
    if not dotenv_path.exists():
        return None

    try:
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in {"API_ADDRESS", "API_BASE_URL", "BEACON_API_ADDRESS"}:
                    return value.strip().strip('"').strip("'")
                continue
            # Backward compatible with one-line address files.
            return line.strip().strip('"').strip("'")
    except OSError as error:
        print(f"Failed reading .env API address: {error}")

    return None


def get_api_base_url():
    raw_address = (
        parse_dotenv_api_address(Path(__file__).resolve().parent / ".env")
        or os.getenv("API_BASE_URL")
        or os.getenv("API_ADDRESS")
        or os.getenv("BEACON_API_ADDRESS")
        or parse_dotenv_api_address(Path(__file__).resolve().parents[1] / ".env")
    )
    if not raw_address:
        raise RuntimeError(
            "Missing API address. Set API_BASE_URL in beacon-node/.env"
        )

    value = raw_address.strip().rstrip("/")
    if "://" not in value:
        value = f"http://{value}"

    parsed = urlparse(value)
    if not parsed.netloc:
        raise RuntimeError(f"Invalid API address: {raw_address}")

    return f"{parsed.scheme}://{parsed.netloc}"


def parse_mid_and_segments(packet_text):
    chunks = [part.strip() for part in packet_text.split("|") if part.strip()]
    machine_id = "unknown-node"
    if chunks and chunks[0].startswith("MID:"):
        machine_id = chunks[0][4:] or machine_id
        chunks = chunks[1:]

    gps_payload = chunks[0] if len(chunks) > 0 else ""
    daph_payload = chunks[1] if len(chunks) > 1 else ""
    water_payload = chunks[2] if len(chunks) > 2 else ""
    return machine_id, gps_payload, daph_payload, water_payload


def parse_nmea_coordinate(value, hemisphere):
    if not value:
        return 0.0

    number = float(value)
    degrees = int(number / 100)
    minutes = number - (degrees * 100)
    decimal = degrees + (minutes / 60.0)
    if hemisphere in {"S", "W"}:
        decimal *= -1.0
    return decimal


def parse_gps_payload(gps_payload):
    if "+CGPSINFO:" not in gps_payload:
        return 0.0, 0.0
    try:
        fields = gps_payload.split(":", 1)[1].split(",")
        lat = parse_nmea_coordinate(fields[0].strip(), fields[1].strip())
        lon = parse_nmea_coordinate(fields[2].strip(), fields[3].strip())
        return lat, lon
    except (IndexError, ValueError):
        return 0.0, 0.0


def parse_metric_payload(payload, prefix):
    metrics = {}
    if not payload.startswith(prefix):
        return metrics

    body = payload[len(prefix) :]
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        key = part[0]
        value = part[1:]
        metrics[key] = value
    return metrics


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def build_sensor_telemetry(gps_payload, daph_payload, water_payload):
    lat, lon = parse_gps_payload(gps_payload)
    daph = parse_metric_payload(daph_payload, "DAPH:")
    water = parse_metric_payload(water_payload, "WATER:")

    return {
        "temperature": to_float(water.get("T"), 0.0),
        "lat": lat,
        "lon": lon,
        "ph": to_float(water.get("P"), 0.0),
        "bylhi": {
            "activity": to_float(daph.get("A"), 0.0),
            "speed_px_s": to_float(daph.get("S"), 0.0),
            "immobility": to_float(daph.get("I"), 0.0),
            "dispersion_px": to_float(daph.get("D"), 0.0),
            "anomaly_score": to_float(daph.get("Z"), 0.0),
            "anomaly_flag": to_int(daph.get("N"), 0),
        },
    }


def post_telemetry(session, api_base_url, machine_id, payload):
    encoded_machine_id = quote(machine_id, safe="")
    url = f"{api_base_url}/data/beacons/{encoded_machine_id}"
    response = session.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.status_code


def main():
    api_base_url = get_api_base_url()
    print(f"Telemetry API base: {api_base_url}")

    cs_pin = getattr(board, os.getenv("LORA_CS_PIN", "D5"))
    reset_pin = getattr(board, os.getenv("LORA_RESET_PIN", "D22"))
    cs = digitalio.DigitalInOut(cs_pin)
    reset = digitalio.DigitalInOut(reset_pin)
    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

    try:
        rfm9x = adafruit_rfm9x.RFM9x(spi, cs, reset, RADIO_FREQ_MHZ)
        print("LoRa receiver initialized successfully")
        print("Waiting for messages...\n")
    except RuntimeError as error:
        print(f"Error initializing LoRa: {error}")
        return

    with requests.Session() as session:
        while True:
            packet = rfm9x.receive(timeout=0.5)
            if packet is None:
                continue

            try:
                packet_text = str(packet, "utf-8")
            except UnicodeDecodeError:
                print(f"Received undecodable packet bytes: {packet}")
                continue

            machine_id, gps_payload, daph_payload, water_payload = parse_mid_and_segments(packet_text)
            telemetry = build_sensor_telemetry(gps_payload, daph_payload, water_payload)
            print(f"Received machine={machine_id}, RSSI={rfm9x.last_rssi} dBm")

            try:
                status = post_telemetry(session, api_base_url, machine_id, telemetry)
                print(f"Posted telemetry ({status}) -> {machine_id}\n")
            except requests.RequestException as error:
                print(f"Telemetry POST failed for machine={machine_id}: {error}\n")


if __name__ == "__main__":
    main()
