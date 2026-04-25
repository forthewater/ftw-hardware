# FTW Hardware

## Developer steps for configuring beacon node

1. Install Raspbian OS on the SD card and set up the Raspberry Pi.
1. Using your hostname (e.g. raspberrypi.local), SSH into the Raspberry Pi and run the following commands to update the system and install necessary dependencies:

   ```bash
   sudo apt update
   sudo apt upgrade -y
   sudo apt install -y git build-essential
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
   sudo apt install -y git build-essential
   ```

1. Enable SPI interface on the Raspberry Pi:

   ```bash
   sudo raspi-config
   ```

   Navigate to "Interfacing Options" > "SPI" and enable it.

1. Clone the FTW Hardware repository and navigate to the beacon node directory:

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

1. Start the beacon node:

   ````bash
   python sensor-node.py
   ```.
   ````
