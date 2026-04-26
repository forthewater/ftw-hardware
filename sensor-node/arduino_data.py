import serial
import time

class WaterMonitor:
    def __init__(self, port='/dev/ttyUSB5', baud_rate=9600):
        # Open the connection
        self.ser = serial.Serial(port, baud_rate, timeout=2)
        # Wait 2 seconds for Arduino to reboot
        time.sleep(2)
        self.ser.flushInput()

    def get_reading(self):
        self.ser.write(b'R')
        self.ser.flush()
        line = self.ser.readline().decode('utf-8').rstrip()

        if line:
            try:
                cond_str, ph_str = line.split(',')
                return {
                    "conductivity": float(cond_str),
                    "ph": float(ph_str)
                }
            except ValueError:
                return {"error": f"Bad data received: {line}"}
        else:
            return {"error": "No response from Arduino"}

    def close(self):
        self.ser.close()


if __name__ == "__main__":
    try:
        sensor = WaterMonitor()
        data = sensor.get_reading()
        print(data)
    except Exception as e:
        print({"error": str(e)})
    finally:
        if 'sensor' in locals():
            sensor.close()
