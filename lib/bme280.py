from breakout_bme280 import BreakoutBME280
from pimoroni_i2c import PimoroniI2C
from config import I2C_PINS
from lib.ulogging import uLogger
from lib.weather_data import WeatherData
from asyncio import sleep

class BME280:
    
    def __init__(self) -> None:
        """
        Init BME280 sensor
        """
        self.logger = uLogger("BME280")
        self.logger.info("Init BME280")
        self.i2c = PimoroniI2C(**I2C_PINS)
        self.bme = BreakoutBME280(self.i2c)
        self.get_readings() # Clear incorrect first value after startup

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
        Async polling of BME280 sensor at a set frequency, retuns readings to weather_data object passed.
        """
        while True:
            try:
                weather_data.add_readings(self.get_readings())
            except Exception as e:
                self.logger.error(f"Failed to add reading to weather data: {e}")
            await sleep(poll_frequency_s)