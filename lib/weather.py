from lib.ulogging import uLogger
from lib.bme280 import BME280
from lib.networking import WirelessNetwork
from asyncio import create_task, get_event_loop, sleep
from lib.weather_data import WeatherData
from config import BME280_POLL_FREQUENCY, ENABLE_RAIN_SENSOR, ENABLE_WIND_SENSORS, ENABLE_LUMINANCE_SENSOR

class WeatherStation:
    """
    Weather Station class to load avaailble sensors and configure sensor polling and data upload services.
    """
    def __init__(self) -> None:
        self.log = uLogger("WeatherStation")
        self.log.info("Init Weather Station")
        self.bme280 = BME280()
        
        # Only initialize wind/rain sensors if enabled
        if ENABLE_RAIN_SENSOR or ENABLE_WIND_SENSORS:
            from lib.wind_rain import WindRainSensors
            self.wind_rain = WindRainSensors()
        else:
            self.wind_rain = None
            
        # Only initialize luminance sensor if enabled
        if ENABLE_LUMINANCE_SENSOR:
            from lib.luminance import LuminanceSensor
            self.luminance = LuminanceSensor()
        else:
            self.luminance = None
            
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
        
        if self.wind_rain:
            # Start wind/rain async tasks (measurement only, no publishing)
            create_task(self.wind_rain.async_poll_all())
        
        # Start combined polling task that gathers ALL sensor data every 60s
        create_task(self.async_combined_polling())
        
        self.loop.run_forever()
    
    async def async_combined_polling(self) -> None:
        """
        Combined polling routine that collects all sensor data together
        and sends it as a single payload every minute.
        
        If individual sensors fail, others will still publish their data.
        """
        while True:
            try:
                combined_readings = {}
                
                # Get BME280 readings (temperature, pressure, humidity)
                try:
                    bme_readings = self.bme280.get_readings()
                    combined_readings.update(bme_readings)
                    
                    # Add sea level pressure if we have pressure and temperature
                    from lib.helpers import get_sea_level_pressure
                    from config import HEIGHT_ABOVE_SEA_LEVEL_M
                    if "pressure" in combined_readings and "temperature" in combined_readings:
                        combined_readings["sea_level_pressure"] = get_sea_level_pressure(
                            combined_readings["pressure"], 
                            combined_readings["temperature"], 
                            HEIGHT_ABOVE_SEA_LEVEL_M
                        )
                except Exception as e:
                    self.log.error(f"BME280 sensor failed: {e}")
                
                # Get luminance readings if enabled
                if self.luminance:
                    try:
                        luminance_readings = self.luminance.get_readings()
                        combined_readings.update(luminance_readings)
                    except Exception as e:
                        self.log.error(f"Luminance sensor failed: {e}")
                
                # Get wind and rain readings if enabled
                if self.wind_rain:
                    try:
                        wind_rain_readings = self.wind_rain.get_all_readings()
                        combined_readings.update(wind_rain_readings)
                    except Exception as e:
                        self.log.error(f"Wind/Rain sensors failed: {e}")
                
                # Only publish if we have at least some valid data
                if combined_readings:
                    self.log.info(f"Combined readings: {combined_readings}")
                    self.weather_data.add_readings(combined_readings)
                else:
                    self.log.warning("No valid sensor data available")
                
            except Exception as e:
                self.log.error(f"Failed in combined polling: {e}")
            
            await sleep(60)