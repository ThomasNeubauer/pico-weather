from lib.ulogging import uLogger
from asyncio import sleep
from time import time, gmtime
from lib.weather_data import WeatherData
from config import (
    RAIN_PIN, WIND_SPEED_PIN, WIND_DIRECTION_PIN,
    RAIN_MM_PER_TICK, WIND_CM_RADIUS, WIND_FACTOR,
    RAIN_POLL_FREQUENCY, WIND_SPEED_POLL_FREQUENCY, WIND_DIRECTION_POLL_FREQUENCY,
    WIND_DIRECTION_OFFSET,
    ENABLE_RAIN_SENSOR, ENABLE_WIND_SENSORS
)
import math
import json
import os

# Try to import MicroPython modules, provide mock implementations for testing
try:
    from machine import Pin, ADC
    MICROPYTHON = True
except ImportError:
    MICROPYTHON = False
    class Pin:
        def __init__(self, pin, mode=None, pull=None):
            self.pin = pin
            self.mode = mode
            self.pull = pull
            self._value = 0
        def value(self):
            return self._value
    
    class ADC:
        def __init__(self, pin):
            self.pin = pin
        def read_u16(self):
            return 32768  # Mid-range value for testing


class RainSensor:
    """
    Rain sensor implementation using a tipping bucket mechanism.
    Each tip of the bucket represents a fixed amount of rainfall (RAIN_MM_PER_TICK).
    """
    
    def __init__(self) -> None:
        """
        Initialize rain sensor with GPIO pin for detecting bucket tips.
        Uses a pull-down resistor configuration.
        """
        self.logger = uLogger("RainSensor")
        self.logger.info("Init Rain Sensor")
        
        self.rain_pin = Pin(RAIN_PIN, Pin.IN, Pin.PULL_DOWN)
        self.logger.info(f"Rain sensor initialized on pin: {RAIN_PIN}")
        
        # Rain data persistence file
        self.rain_file = "rain_log.txt"
        
        # Last known state of the rain pin
        self.last_rain_trigger = False
        
        # Initialize rain log file if it doesn't exist
        if not self._file_exists(self.rain_file):
            self.logger.info("Creating new rain log file")
            with open(self.rain_file, "w") as f:
                f.write("")
    
    def _file_exists(self, filename: str) -> bool:
        """Check if a file exists."""
        try:
            return os.stat(filename)[0] & 0x4000 == 0
        except OSError:
            return False
    
    def _log_rain_tip(self) -> None:
        """
        Log a rain bucket tip event with timestamp.
        """
        timestamp = self._get_current_timestamp()
        self.logger.info(f"Rain bucket tip detected at: {timestamp}")
        
        # Read existing entries
        rain_entries = []
        if self._file_exists(self.rain_file):
            try:
                with open(self.rain_file, "r") as f:
                    rain_entries = f.read().split("\n")
            except Exception as e:
                self.logger.error(f"Failed to read rain log: {e}")
                rain_entries = []
        
        # Add new entry
        rain_entries.append(timestamp)
        
        # Limit file size - keep only recent entries to prevent filesystem bloat
        # Each entry is approximately 20-25 bytes, limit to ~2000 entries = ~40-50KB
        max_entries = 2000
        if len(rain_entries) > max_entries:
            self.logger.info(f"Rain log exceeded {max_entries} entries, trimming to last {max_entries}")
            rain_entries = rain_entries[-max_entries:]
        
        # Write updated entries back to file
        try:
            with open(self.rain_file, "w") as f:
                f.write("\n".join(rain_entries))
            self.logger.info("Rain tip logged successfully")
        except Exception as e:
            self.logger.error(f"Failed to write rain log: {e}")
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        dt = gmtime()
        return f"{dt[0]:04d}-{dt[1]:02d}-{dt[2]:02d}T{dt[3]:02d}:{dt[4]:02d}:{dt[5]:02d}Z"
    
    def _timestamp_to_epoch(self, timestamp_str: str) -> float:
        """Convert ISO timestamp string to epoch time."""
        try:
            # Parse: YYYY-MM-DDTHH:MM:SSZ
            year = int(timestamp_str[0:4])
            month = int(timestamp_str[5:7])
            day = int(timestamp_str[8:10])
            hour = int(timestamp_str[11:13])
            minute = int(timestamp_str[14:16])
            second = int(timestamp_str[17:19])
            
            from time import mktime
            # Note: mktime expects local time, but we're using GMT
            # For simplicity, we'll use the basic approach
            return mktime((year, month, day, hour, minute, second, 0, 0, 0))
        except Exception as e:
            self.logger.error(f"Failed to parse timestamp {timestamp_str}: {e}")
            return 0
    
    def check_rain_trigger(self) -> bool:
        """
        Check if rain sensor has triggered (bucket tipped).
        Returns True if a new tip is detected.
        """
        rain_sensor_trigger = self.rain_pin.value()
        
        if rain_sensor_trigger and not self.last_rain_trigger:
            self.logger.info("Rain bucket tip detected!")
            self._log_rain_tip()
            self.last_rain_trigger = rain_sensor_trigger
            return True
        
        self.last_rain_trigger = rain_sensor_trigger
        return False
    
    def get_rainfall_data(self, seconds_since_last: float = 0) -> dict:
        """
        Calculate rainfall data based on logged tips.
        Returns dictionary with various rainfall measurements.
        
        Args:
            seconds_since_last: Time in seconds since last reading (for rate calculations)
            
        Returns:
            dict: {
                'rain_mm': total rain since last reading,
                'rain_per_hour': rain in last hour,
                'rain_per_day': rain today,
                'rain_tips': number of tips since last reading
            }
        """
        rain_mm = 0.0
        rain_per_hour = 0.0
        rain_today = 0.0
        rain_tips = 0
        
        if not self._file_exists(self.rain_file):
            return {
                'rain_mm': 0.0,
                'rain_per_hour': 0.0,
                'rain_per_day': 0.0,
                'rain_tips': 0
            }
        
        try:
            with open(self.rain_file, "r") as f:
                rain_entries = f.read().split("\n")
        except Exception as e:
            self.logger.error(f"Failed to read rain log: {e}")
            return {
                'rain_mm': 0.0,
                'rain_per_hour': 0.0,
                'rain_per_day': 0.0,
                'rain_tips': 0
            }
        
        current_time = time()
        current_day = gmtime()[2]  # Day of month
        
        new_entries = []
        
        for entry in rain_entries:
            if not entry.strip():
                continue
                
            entry_time = self._timestamp_to_epoch(entry)
            if entry_time == 0:
                continue
                
            # Calculate time difference from now
            time_diff = current_time - entry_time
            
            # Count for rain since last reading
            if seconds_since_last > 0 and time_diff < seconds_since_last:
                rain_mm += RAIN_MM_PER_TICK
                rain_tips += 1
            
            # Count for last hour
            if time_diff < 3600:  # 1 hour
                rain_per_hour += RAIN_MM_PER_TICK
            
            # Count for today
            entry_date = gmtime(entry_time)
            if entry_date[2] == current_day:  # Same day
                rain_today += RAIN_MM_PER_TICK
                new_entries.append(entry)  # Keep for future reads
            else:
                # This is from a previous day, count towards totals but don't keep
                rain_today += RAIN_MM_PER_TICK
        
        # Write back only today's entries to keep file size manageable
        try:
            with open(self.rain_file, "w") as f:
                f.write("\n".join(new_entries))
        except Exception as e:
            self.logger.error(f"Failed to update rain log: {e}")
        
        return {
            'rain_mm': round(rain_mm, 3),
            'rain_per_hour': round(rain_per_hour, 3),
            'rain_per_day': round(rain_today, 3),
            'rain_tips': rain_tips
        }
    
    async def async_poll_rain(self, weather_data: WeatherData, poll_frequency_s: int) -> None:
        """
        Async polling for rain sensor.
        Checks for bucket tips and logs them.
        Also periodically calculates rainfall data.
        """
        last_poll_time = time()
        
        while True:
            try:
                # Check for immediate rain triggers
                self.check_rain_trigger()
                
                # Periodically calculate and report rainfall data
                current_time = time()
                seconds_since_last = current_time - last_poll_time
                
                if seconds_since_last >= poll_frequency_s:
                    rain_data = self.get_rainfall_data(seconds_since_last)
                    weather_data.add_readings(rain_data)
                    last_poll_time = current_time
                
            except Exception as e:
                self.logger.error(f"Failed in rain polling: {e}")
            
            await sleep(1)  # Check frequently for rain triggers


class WindSpeedSensor:
    """
    Wind speed sensor implementation using an anemometer.
    Measures rotations to calculate wind speed in m/s.
    """
    
    def __init__(self) -> None:
        """
        Initialize wind speed sensor with GPIO pin.
        Uses a pull-up resistor configuration.
        """
        self.logger = uLogger("WindSpeedSensor")
        self.logger.info("Init Wind Speed Sensor")
        
        self.wind_speed_pin = Pin(WIND_SPEED_PIN, Pin.IN, Pin.PULL_UP)
        self.logger.info(f"Wind speed sensor initialized on pin: {WIND_SPEED_PIN}")
        
        # Wind speed calculation parameters
        self.radius_cm = WIND_CM_RADIUS
        self.wind_factor = WIND_FACTOR
        
        # For storing wind speed samples
        self.speed_samples = []
        self.max_samples = 10  # Store last 10 speed readings for averaging
    
    def measure_wind_speed(self, sample_time_ms: int = 1000) -> float:
        """
        Measure wind speed over a sample period.
        
        Args:
            sample_time_ms: Sample time in milliseconds (default: 1000ms = 1 second)
            
        Returns:
            float: Wind speed in meters per second
        """
        # Get initial sensor state
        state = self.wind_speed_pin.value()
        
        # Array to log state change times
        ticks = []
        
        start_time = time() * 1000  # Convert to ms
        
        # Sample for the specified duration
        while (time() * 1000) - start_time <= sample_time_ms:
            now = self.wind_speed_pin.value()
            if now != state:  # Sensor state changed
                # Record the time of the change
                ticks.append(time() * 1000)
                state = now
        
        # Need at least 2 ticks to calculate speed
        if len(ticks) < 2:
            return 0.0
        
        # Calculate average tick time in milliseconds
        average_tick_ms = (ticks[-1] - ticks[0]) / (len(ticks) - 1)
        
        if average_tick_ms == 0:
            return 0.0
        
        # Calculate rotation speed in Hz (two ticks per rotation for most anemometers)
        rotation_hz = (1000 / average_tick_ms) / 2
        
        # Calculate circumference in cm
        circumference = self.radius_cm * 2.0 * math.pi
        
        # Calculate wind speed in cm/s, then convert to m/s
        wind_cm_per_s = rotation_hz * circumference
        wind_m_per_s = wind_cm_per_s * self.wind_factor
        
        return round(wind_m_per_s, 2)
    
    def get_current_wind_speed(self) -> dict:
        """
        Get current wind speed reading.
        
        Returns:
            dict: {
                'wind_speed': current wind speed in m/s,
                'wind_speed_avg': average wind speed over recent samples
            }
        """
        # Take multiple samples and average for better accuracy
        samples = []
        for _ in range(3):  # Take 3 samples
            speed = self.measure_wind_speed(500)  # 500ms sample time
            if speed > 0:  # Only include valid readings
                samples.append(speed)
        
        if samples:
            current_speed = round(sum(samples) / len(samples), 2)
        else:
            current_speed = 0.0
        
        # Update sample history
        self.speed_samples.append(current_speed)
        if len(self.speed_samples) > self.max_samples:
            self.speed_samples = self.speed_samples[-self.max_samples:]
        
        # Calculate average
        if self.speed_samples:
            avg_speed = round(sum(self.speed_samples) / len(self.speed_samples), 2)
        else:
            avg_speed = 0.0
        
        # Calculate gust (max recent speed)
        gust_speed = round(max(self.speed_samples), 2) if self.speed_samples else 0.0
        
        return {
            'wind_speed': current_speed,
            'wind_speed_avg': avg_speed,
            'wind_gust': gust_speed
        }
    
    async def async_poll_wind_speed(self, weather_data: WeatherData, poll_frequency_s: int) -> None:
        """
        Async polling for wind speed sensor.
        Measures wind speed at the specified frequency.
        """
        while True:
            try:
                wind_data = self.get_current_wind_speed()
                weather_data.add_readings(wind_data)
            except Exception as e:
                self.logger.error(f"Failed in wind speed polling: {e}")
            
            await sleep(poll_frequency_s)


class WindDirectionSensor:
    """
    Wind direction sensor implementation using an analog potentiometer.
    Converts analog voltage to wind direction in degrees.
    """
    
    # ADC to degrees mapping for 16 compass positions (22.5° each)
    # These values are typical for analog wind vane sensors
    ADC_TO_DEGREES = (
        2.533, 1.308, 1.487, 0.270, 0.300, 0.212, 0.595, 0.408,
        0.926, 0.789, 2.031, 1.932, 3.046, 2.667, 2.859, 2.265
    )
    
    def __init__(self) -> None:
        """
        Initialize wind direction sensor with analog pin.
        """
        self.logger = uLogger("WindDirectionSensor")
        self.logger.info("Init Wind Direction Sensor")
        
        self.wind_dir_pin = ADC(WIND_DIRECTION_PIN)
        self.logger.info(f"Wind direction sensor initialized on pin: {WIND_DIRECTION_PIN}")
        
        self.direction_offset = WIND_DIRECTION_OFFSET
    
    def read_voltage(self) -> float:
        """
        Read the analog voltage from the wind direction sensor.
        Returns voltage in volts (0-3.3V).
        """
        try:
            # ADC reads 0-65535 for 0-3.3V
            raw_value = self.wind_dir_pin.read_u16()
            voltage = raw_value / 65535.0 * 3.3
            return voltage
        except Exception as e:
            self.logger.error(f"Failed to read wind direction voltage: {e}")
            return 0.0
    
    def get_wind_direction(self) -> float:
        """
        Get current wind direction in degrees (0-359.9).
        
        Returns:
            float: Wind direction in degrees, adjusted by offset
        """
        voltage = self.read_voltage()
        
        # Find the closest matching value in ADC_TO_DEGREES
        closest_index = 0
        closest_value = float('inf')
        
        for i in range(len(self.ADC_TO_DEGREES)):
            distance = abs(self.ADC_TO_DEGREES[i] - voltage)
            if distance < closest_value:
                closest_value = distance
                closest_index = i
        
        # Calculate base wind direction (0-348.75 degrees, in 22.5° increments)
        wind_direction = closest_index * 22.5
        
        # Apply offset and ensure it's within 0-360 range
        adjusted_direction = (wind_direction + self.direction_offset) % 360
        
        self.logger.info(f"Wind direction: voltage={voltage:.3f}V, raw={wind_direction:.1f}°, adjusted={adjusted_direction:.1f}°")
        
        return round(adjusted_direction, 1)
    
    async def async_poll_wind_direction(self, weather_data: WeatherData, poll_frequency_s: int) -> None:
        """
        Async polling for wind direction sensor.
        Reads wind direction at the specified frequency.
        """
        while True:
            try:
                wind_direction = self.get_wind_direction()
                weather_data.add_readings({
                    'wind_direction': wind_direction
                })
            except Exception as e:
                self.logger.error(f"Failed in wind direction polling: {e}")
            
            await sleep(poll_frequency_s)


class WindRainSensors:
    """
    Combined wind and rain sensor manager for convenience.
    Provides unified interface for weather station.
    """
    
    def __init__(self) -> None:
        """
        Initialize all wind and rain sensors.
        """
        self.logger = uLogger("WindRainSensors")
        self.logger.info("Init Wind & Rain Sensors")
        
        # Only initialize sensors that are enabled
        self.rain_sensor = RainSensor() if ENABLE_RAIN_SENSOR else None
        self.wind_speed_sensor = WindSpeedSensor() if ENABLE_WIND_SENSORS else None
        self.wind_direction_sensor = WindDirectionSensor() if ENABLE_WIND_SENSORS else None
        
        if not ENABLE_RAIN_SENSOR:
            self.logger.info("Rain sensor disabled via config")
        if not ENABLE_WIND_SENSORS:
            self.logger.info("Wind sensors disabled via config")
    
    async def async_poll_all(self, weather_data: WeatherData) -> None:
        """
        Start async polling for all wind and rain sensors.
        Each sensor can have its own polling frequency.
        """
        # Start individual sensor polling tasks
        from asyncio import create_task
        
        if ENABLE_RAIN_SENSOR and self.rain_sensor:
            create_task(self.rain_sensor.async_poll_rain(weather_data, RAIN_POLL_FREQUENCY))
        
        if ENABLE_WIND_SENSORS and self.wind_speed_sensor:
            create_task(self.wind_speed_sensor.async_poll_wind_speed(weather_data, WIND_SPEED_POLL_FREQUENCY))
            
        if ENABLE_WIND_SENSORS and self.wind_direction_sensor:
            create_task(self.wind_direction_sensor.async_poll_wind_direction(weather_data, WIND_DIRECTION_POLL_FREQUENCY))
    
    def get_all_readings(self) -> dict:
        """
        Get current readings from all wind and rain sensors.
        Useful for manual polling or testing.
        """
        readings = {}
        
        # Rain data
        if ENABLE_RAIN_SENSOR and self.rain_sensor:
            rain_data = self.rain_sensor.get_rainfall_data()
            readings.update(rain_data)
        
        # Wind speed data
        if ENABLE_WIND_SENSORS and self.wind_speed_sensor:
            wind_speed_data = self.wind_speed_sensor.get_current_wind_speed()
            readings.update(wind_speed_data)
        
        # Wind direction data
        if ENABLE_WIND_SENSORS and self.wind_direction_sensor:
            wind_direction = self.wind_direction_sensor.get_wind_direction()
            readings['wind_direction'] = wind_direction
        
        return readings