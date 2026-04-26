# FTW Hardware

## Developer steps for configuring beacon node

1. Install Raspbian OS on the SD card and set up the Raspberry Pi.
1. Using your hostname (e.g. raspberrypi.local), SSH into the Raspberry Pi and run the following commands to update the system and install necessary dependencies:

   ```bash
   sudo apt update
   sudo apt upgrade -y
   sudo apt install -y git build-essential swig
   ```

1. Enable SPI interface on the Raspberry Pi:

   ```bash
   sudo raspi-config
   ```

   Navigate to "Interfacing Options" > "SPI" and enable it.

1. Clone the FTW Hardware repository and navigate to the beacon node directory:

   ```bash
   git clone https://github.com/forthewater/ftw-hardware.git
   cd ftw-hardware/beacon-node
   ```

1. Create Python virtual environment and install dependencies:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

   *Alternatively, to install directly to the system without a virtual environment:*

   ```bash
   pip install -r requirements.txt --break-system-packages
   ```

1. Start the beacon node:

   ```bash
   python beacon-node.py
   ```

## Developer steps for configuring sensor node

1. Install Raspbian OS on the SD card and set up the Raspberry Pi.
1. Using your hostname (e.g. raspberrypi.local), SSH into the Raspberry Pi and run the following commands to update the system and install necessary dependencies:

   ```bash
   sudo apt update
   sudo apt upgrade -y
   sudo apt install -y git build-essential swig
   ```

1. Enable SPI interface on the Raspberry Pi:

   ```bash
   sudo raspi-config
   ```

   Navigate to "Interfacing Options" > "SPI" and enable it.

1. Enable the serial interface for the SIM7600 module:

   ```bash
   sudo raspi-config
   ```

   Navigate to "Interface Options" > "Serial Port" and set:
   - "Would you like a login shell to be accessible over serial?" -> **No**
   - "Would you like the serial port hardware to be enabled?" -> **Yes**

   Reboot to apply the change:

   ```bash
   sudo reboot
   ```

1. Enable camera interface:

   ```bash
   sudo raspi-config
   ```

   Navigate to "Interface Options" > "Camera" and enable it.

1. Clone the FTW Hardware repository and navigate to the sensor node directory:

   ```bash
   git clone https://github.com/forthewater/ftw-hardware.git
   cd ftw-hardware/sensor-node
   ```

1. Create Python virtual environment and install dependencies:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

   *Alternatively, to install directly to the system without a virtual environment:*

   ```bash
   pip install -r requirements.txt --break-system-packages
   ```

1. Start the sensor node:

   ```bash
   python sensor-node.py
   ```

## Daphnia activity monitor

The sensor node now appends daphnia activity metrics to each LoRa payload in this format:
`DAPH:A<activity>,S<speed>,I<immobility>,D<dispersion>,N<anomaly>`

Useful environment variables:
- `ENABLE_DAPHNIA` (default `1`) set to `0` to disable camera analysis.
- `DAPHNIA_CAMERA_INDEX` (default `0`) selects the OpenCV camera.
- `DAPHNIA_WINDOW_SECONDS` (default `8`) capture window length.
- `DAPHNIA_FPS` (default `10`) target frame rate.

Run monitor only (without LoRa/SIM7600) from `sensor-node/`:

```bash
python daphnia_monitor.py --camera 0 --window-seconds 10 --fps 10
```

Run hardware-free unit tests from `sensor-node/`:

```bash
python -m unittest discover -s tests -p "test_*.py"
```
