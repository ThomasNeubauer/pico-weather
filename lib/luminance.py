from lib.ulogging import uLogger
from pimoroni_i2c import PimoroniI2C
from config import I2C_PINS, ENABLE_LUMINANCE_SENSOR
from breakout_ltr559 import BreakoutLTR559


class LuminanceSensor:
    """
    LTR-559 luminance sensor implementation for Enviro Weather board.
    Provides lux readings via I2C interface.
    
    Uses the Pimoroni BreakoutLTR559 library to read light levels in lux.
    The LTR-559 is a digital light sensor with I2C interface that provides
    ambient light measurements in lux.
    """

    def __init__(self) -> None:
        """
        Initialize LTR-559 luminance sensor.
        
        Reuses the same I2C bus as other sensors (BME280, etc.)
        """
        self.logger = uLogger("LuminanceSensor")
        self.logger.info("Init Luminance Sensor")

        # Initialize I2C - reuse same bus as BME280
        self.i2c = PimoroniI2C(**I2C_PINS)
        self.logger.info(f"Luminance sensor I2C initialized on pins: {I2C_PINS}")

        # Initialize LTR-559 sensor
        try:
            self.sensor = BreakoutLTR559(self.i2c)
            self.logger.info("LTR-559 luminance sensor initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize LTR-559 sensor: {e}")
            raise RuntimeError(f"LTR-559 initialization failed: {e}")

    def get_readings(self) -> dict:
        """
        Get current luminance reading.
        
        Returns:
            dict: {"luminance": lux_value} where lux_value is light level in lux,
                  rounded to 2 decimal places. Returns None on failure.
        """
        try:
            ltr_data = self.sensor.get_reading()
            luminance = round(ltr_data[BreakoutLTR559.LUX], 2)

            self.logger.info(f"Luminance: {luminance} lux")
            return {"luminance": luminance}

        except Exception as e:
            self.logger.error(f"Failed to read luminance: {e}")
            return {"luminance": None}
