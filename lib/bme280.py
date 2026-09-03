from breakout_bme280 import BreakoutBME280
from pimoroni_i2c import PimoroniI2C
from config import I2C_PINS, HEIGHT_ABOVE_SEA_LEVEL_M
from lib.ulogging import uLogger
from lib.weather_data import WeatherData
from asyncio import sleep
from lib.helpers import get_sea_level_pressure
import time

class BME280:
    
    def __init__(self) -> None:
        """
        Init BME280 sensor using Pimoroni breakout library
        Tries multiple I2C addresses (0x77, 0x76) and provides detailed error info
        """
        self.logger = uLogger("BME280")
        self.logger.info("Init BME280")
        
        # Initialize I2C
        self.i2c = PimoroniI2C(**I2C_PINS)
        self.logger.info(f"I2C initialized on pins: {I2C_PINS}")
        
        # Try to scan for I2C devices to help diagnose issues
        try:
            i2c_devices = self.i2c.scan()
            self.logger.info(f"I2C devices found: {i2c_devices}")
        except Exception as e:
            self.logger.error(f"I2C scan failed: {e}")
        
        # Try common BME280 I2C addresses
        addresses = [0x77, 0x76]
        bme_initialized = False
        last_error = None
        
        for address in addresses:
            try:
                self.bme = BreakoutBME280(self.i2c, address)
                self.logger.info(f"Attempting BME280 init with address 0x{address:02x}")
                
                # Clear incorrect first value after startup - do a dummy read first
                # as per Pimoroni's recommendation
                self.bme.read()  # Dummy read to clear register contents
                time.sleep(0.1)
                
                # Now get the actual first reading
                self.get_readings()
                bme_initialized = True
                self.logger.info(f"BME280 initialized successfully with address 0x{address:02x}")
                break
                
            except Exception as e:
                last_error = e
                self.logger.error(f"Failed to initialize BME280 at address 0x{address:02x}: {e}")
                continue
        
        if not bme_initialized:
            self.logger.error("Failed to initialize BME280 with all addresses")
            self.logger.error("This could be due to:")
            self.logger.error("- Wrong I2C pins (check I2C_PINS in config.py)")
            self.logger.error("- Missing Pimoroni firmware libraries")
            self.logger.error("- Sensor not connected or powered")
            self.logger.error("- Sensor using non-standard I2C address")
            raise RuntimeError(f"BME280 initialization failed with all addresses: {last_error}")

    def get_readings(self) -> dict:
        """
        Return a set of readings from the BME280 chip in a dictionary.
        {"temperature": float degrees c,"pressure": float mbar, "humidity": int %}
        """
        temperature, pressure, humidity = self.bme.read()
        readings = {}
        readings["temperature"] = round(temperature, 2)
        readings["pressure"] = round(pressure / 100, 2)
        readings["humidity"] = round(humidity, 2)

        self.logger.info(f"BME 280 readings collected: {readings}")

        return readings
    
    async def async_poll_readings(self, weather_data: WeatherData, poll_frequency_s: int) -> None:
        """
        Async polling of BME280 sensor at a set frequency, returns readings to weather_data object passed.
        """
        while True:
            try:
                readings = self.get_readings()
                readings["sea_level_pressure"] = get_sea_level_pressure(readings["pressure"], readings["temperature"], HEIGHT_ABOVE_SEA_LEVEL_M)
                weather_data.add_readings(readings)
            except Exception as e:
                self.logger.error(f"Failed to add reading to weather data: {e}")
            await sleep(poll_frequency_s)