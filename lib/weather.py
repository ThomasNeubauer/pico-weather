from lib.ulogging import uLogger
from lib.bme280 import BME280
from lib.networking import WirelessNetwork
from asyncio import create_task, get_event_loop
from lib.weather_data import WeatherData
from config import BME280_POLL_FREQUENCY

class WeatherStation:
    """
    Weather Station class to load avaailble sensors and configure sensor polling and data upload services.
    """
    def __init__(self) -> None:
        self.log = uLogger("WeatherStation")
        self.log.info("Init Weather Station")
        self.bme280 = BME280()
        self.wifi = WirelessNetwork()
        self.weather_data = WeatherData()
        self.loop = get_event_loop()

    def startup(self) -> None:
        """
        Start weather data services
        """
        self.log.info("Starting Weather Station")
        self.wifi.startup()
        self.weather_data.startup()
        create_task(self.bme280.async_poll_readings(self.weather_data, BME280_POLL_FREQUENCY))
        
        self.loop.run_forever()