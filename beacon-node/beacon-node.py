import board
import busio
import digitalio
import adafruit_rfm9x

# Define radio frequency for your Ra-01 module
RADIO_FREQ_MHZ = 433.0

# Define pins based on our wiring
CS = digitalio.DigitalInOut(board.CE0)
RESET = digitalio.DigitalInOut(board.D22)

# Initialize SPI bus and LoRa radio
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
try:
    rfm9x = adafruit_rfm9x.RFM9x(spi, CS, RESET, RADIO_FREQ_MHZ)
    print("LoRa Receiver initialized successfully!")
    print("Waiting for messages...\n")
except RuntimeError as error:
    print("Error initializing LoRa:", error)
    exit()

while True:
    # timeout=0.5 means it checks for a packet for half a second, then moves on
    packet = rfm9x.receive(timeout=0.5)

    if packet is not None:
        try:
            packet_text = str(packet, "utf-8")
            print(f"Received Message: {packet_text}")
        except UnicodeDecodeError:
            print(f"Received raw bytes: {packet}")

        print(f"Signal Strength (RSSI): {rfm9x.last_rssi} dBm\n")
