import os

import board
import busio
import digitalio
import adafruit_rfm9x


def resolve_board_pin(env_name, default_pin_name):
    pin_name = os.getenv(env_name, default_pin_name)
    pin = getattr(board, pin_name, None)
    if pin is None:
        raise ValueError(f"Invalid board pin '{pin_name}' for {env_name}")
    return pin_name, pin


def init_lora_radio():
    if os.getenv("ENABLE_LORA", "1") != "1":
        print("LoRa disabled (ENABLE_LORA != 1).")
        return None, None, None, None

    radio_freq_mhz = float(os.getenv("LORA_RADIO_FREQ_MHZ", "433.0"))
    tx_power = int(os.getenv("LORA_TX_POWER", "13"))
    cs_name, cs_pin = resolve_board_pin("LORA_CS_PIN", "D5")
    reset_name, reset_pin = resolve_board_pin("LORA_RESET_PIN", "D22")

    lora_cs = None
    lora_reset = None
    lora_spi = None
    try:
        lora_cs = digitalio.DigitalInOut(cs_pin)
        lora_reset = digitalio.DigitalInOut(reset_pin)
        lora_spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        radio = adafruit_rfm9x.RFM9x(lora_spi, lora_cs, lora_reset, radio_freq_mhz)
        radio.tx_power = tx_power
        print(
            f"LoRa initialized (freq={radio_freq_mhz}MHz, tx={tx_power}dBm, "
            f"CS={cs_name}, RESET={reset_name})."
        )
        return radio, lora_cs, lora_reset, lora_spi
    except Exception as error:
        cleanup_lora_resources(lora_cs, lora_reset, lora_spi)
        print(f"LoRa init failed: {type(error).__name__}: {error}")
        if "GPIO busy" in str(error):
            print(
                "Hint: another process is using this GPIO. "
                "Stop the conflicting process, reboot, or choose a different pin via "
                "LORA_RESET_PIN/LORA_CS_PIN."
            )
        raise


def cleanup_lora_resources(*resources):
    for resource in resources:
        if resource is not None and hasattr(resource, "deinit"):
            resource.deinit()

