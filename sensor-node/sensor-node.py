import time
import serial
import board
import busio
import digitalio
import adafruit_rfm9x

# --- 1. LoRa Setup ---
RADIO_FREQ_MHZ = 433.0
CS = digitalio.DigitalInOut(board.D5) # Using GPIO 5 as configured previously
RESET = digitalio.DigitalInOut(board.D22)
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

try:
    rfm9x = adafruit_rfm9x.RFM9x(spi, CS, RESET, RADIO_FREQ_MHZ)
    rfm9x.tx_power = 13
    print("LoRa module initialized.")
except RuntimeError as error:
    print("LoRa Error:", error)
    exit()

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

# --- 3. Initialize GPS ---
print("Powering on GPS...")
# AT+CGPS=1 turns on the GNSS engine
send_at_command("AT+CGPS=1", 2)

print("Starting transmission loop...")

# --- 4. Main Loop ---
while True:
    # Request GPS info
    gps_data = send_at_command("AT+CGPSINFO", 1)

    # The response looks like: +CGPSINFO: 3113.343286,N,12121.234064,E,250311,072809.3,44.1,0.0,0
    # If no fix yet, it looks like: +CGPSINFO: ,,,,,,,,

    payload = "Waiting for GPS fix..."
    lines = gps_data.split('\n')

    for line in lines:
        if "+CGPSINFO:" in line:
            clean_line = line.strip()
            # Check if coordinates are empty
            if ",,,,,,,," in clean_line:
                print("No GPS fix. Ensure the GPS antenna is outside with a clear view of the sky.")
            else:
                payload = clean_line # We have a fix!
                print(f"GPS Fix acquired!")
            break

    # Send the payload via LoRa
    print(f"Transmitting over LoRa: {payload}")
    rfm9x.send(bytes(payload, "utf-8"))

    print("-" * 30)
    time.sleep(5) # Wait 5 seconds before checking and sending again
