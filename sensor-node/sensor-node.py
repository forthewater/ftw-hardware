import time
import board
import busio
import digitalio
import adafruit_rfm9x

# Define radio frequency for your Ra-01 module
RADIO_FREQ_MHZ = 433.0

# Define pins based on our wiring
CS = digitalio.DigitalInOut(board.D5)
RESET = digitalio.DigitalInOut(board.D22)

# Initialize SPI bus and LoRa radio
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

try:
    rfm9x = adafruit_rfm9x.RFM9x(spi, CS, RESET, RADIO_FREQ_MHZ)
    print("LoRa Sender initialized successfully!")
    rfm9x.tx_power = 13  # transmit power (default is 13 dBm, max is 23 dBm)
except RuntimeError as error:
    print("Error initializing LoRa:", error)
    exit()

counter = 1

print("Starting transmission loop...")
while True:
    message = f"Hello from Pi A! (Message #{counter})"
    print(f"Sending: {message}")

    rfm9x.send(bytes(message, "utf-8"))

    counter += 1
    time.sleep(2)  # Wait 2 seconds before sending the next message

