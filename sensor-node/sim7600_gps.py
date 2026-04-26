import serial
import time


DEFAULT_SERIAL_PORT = "/dev/serial0"
DEFAULT_BAUD_RATE = 115200


def open_sim7600_serial(port=DEFAULT_SERIAL_PORT, baud_rate=DEFAULT_BAUD_RATE, timeout=1):
    sim_serial = serial.Serial(port, baud_rate, timeout=timeout)
    print("SIM7600 Serial port opened.")
    return sim_serial


def send_at_command(sim_serial, command, wait_time=1):
    """Sends an AT command to the SIM7600 and returns the response."""
    sim_serial.write((command + "\r\n").encode())
    time.sleep(wait_time)
    response = ""
    while sim_serial.in_waiting:
        response += sim_serial.read(sim_serial.in_waiting).decode("utf-8", errors="ignore")
    return response


def extract_gps_payload(gps_data):
    payload = "Waiting for GPS fix..."
    lines = gps_data.split("\n")

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


def power_on_gps(sim_serial):
    # AT+CGPS=1 turns on the GNSS engine
    send_at_command(sim_serial, "AT+CGPS=1", 2)


def read_gps_payload(sim_serial):
    gps_data = send_at_command(sim_serial, "AT+CGPSINFO", 1)
    return extract_gps_payload(gps_data)


def close_sim7600_serial(sim_serial):
    if sim_serial is not None:
        sim_serial.close()

