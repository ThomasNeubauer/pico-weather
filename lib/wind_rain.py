from lib.ulogging import uLogger
from asyncio import sleep
from time import time, gmtime
from lib.weather_data import WeatherData
from config import (
    RAIN_PIN, WIND_SPEED_PIN, WIND_DIRECTION_PIN,
    RAIN_MM_PER_TICK, WIND_CM_RADIUS, WIND_FACTOR,
    RAIN_POLL_FREQUENCY, WIND_DIRECTION_POLL_FREQUENCY,
    WIND_DIRECTION_OFFSET, WIND_GUST_WINDOW_SECONDS,
    ENABLE_RAIN_SENSOR, ENABLE_WIND_SENSORS
)
import math
import json
import os

# Try to import _thread for multicore support
try:
    import _thread
    HAS_THREAD = True
except ImportError:
    HAS_THREAD = False
    # Mock for testing on non-MicroPython platforms
    class _thread:
        @staticmethod
        def allocate_lock():
            class MockLock:
                def __enter__(self): pass
                def __exit__(self, *args): pass
                def acquire(self): pass
                def release(self): pass
            return MockLock()
        @staticmethod
        def start_new_thread(func, args):
            return None

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

# Import time functions - use MicroPython versions if available
try:
    from time import ticks_ms, ticks_diff
except ImportError:
    # Mock implementations for standard Python
    import time as time_module
    def ticks_ms():
        return int(time_module.time() * 1000)

    def ticks_diff(a, b):
        return a - b


class MulticoreWindSpeedSensor:
    """
    Multicore wind speed sensor implementation using a dedicated thread on Core 2.
    Uses blocking continuous polling to capture 100% of reed switch transitions.
    
    This solves the plateau effect and under-sampling issues at high wind speeds
    by polling the wind speed pin continuously within each sample window (250ms at 4Hz).
    
    Architecture:
    - Dedicated thread on Core 2 runs constant_poll_wind_speed()
    - sample_wind_poll() blocks and polls continuously for full sample_ms duration
    - Samples stored in pre-allocated list for 60-second window
    - Thread-safe access via locks for shared data
    """

    def __init__(self) -> None:
        self.log = uLogger("MulticoreWindSpeedSensor")
        self.log.info("Init Multicore Wind Speed Sensor")
        
        # Thread locks for safe data access
        self.pending_wind_data_lock = _thread.allocate_lock()
        self.samples_lock = _thread.allocate_lock()
        
        # Wind speed pin configuration
        self.wind_speed_pin = Pin(WIND_SPEED_PIN, Pin.IN, Pin.PULL_UP)
        self.log.info(f"Wind speed sensor initialized on pin: {WIND_SPEED_PIN}")
        
        # Sample configuration
        self.monitoring_window_s = 60
        self.sample_hz = 4
        self.sample_ms = 1000 / self.sample_hz
        
        # Pre-allocated samples storage (240 samples = 60s * 4Hz)
        self.samples = [[]] * (self.monitoring_window_s * self.sample_hz)
        self.samples_max_list_id = len(self.samples) - 1
        
        # Wind speed calculation parameters (from config)
        self.WIND_CM_RADIUS = WIND_CM_RADIUS
        self.WIND_FACTOR = WIND_FACTOR
        
        # Data storage
        self.pending_wind_data = []
        self.debug = False
        
        # Processing overhead compensation
        self.processing_overhead_poll_count = 0
        self.last_loop_overhead_ms = 0
        self.remaining_loop_overhead_ms = 0
        self.previous_loop_time_ms = 0
        self.cached_samples = []
        
        # Gust calculation window (from config)
        self.gust_rolling_average_duration_s = WIND_GUST_WINDOW_SECONDS

    def init_wind_poll_thread(self) -> None:
        self.log.info("Starting wind poll thread on Core 2")
        self.wind_poll_thread = _thread.start_new_thread(self.constant_poll_wind_speed, ())

    def discard_overhead_compensation_poll(self) -> None:
        if self.remaining_loop_overhead_ms >= self.sample_ms:
            self.remaining_loop_overhead_ms -= self.sample_ms
        else:
            start = ticks_ms()
            while ticks_diff(ticks_ms(), start) <= (self.sample_ms - self.last_loop_overhead_ms):
                pass
            self.remaining_loop_overhead_ms = 0
        self.processing_overhead_poll_count += 1

    def sample_wind_poll(self) -> list:
        previous_wind_pin_state = self.wind_speed_pin.value()
        ticks = []
        start = ticks_ms()
        while ticks_diff(ticks_ms(), start) <= self.sample_ms:
            current_wind_pin_state = self.wind_speed_pin.value()
            if current_wind_pin_state != previous_wind_pin_state:
                ticks.append(ticks_ms())
                previous_wind_pin_state = current_wind_pin_state
        return ticks

    def record_sample_datapoint(self, sample_id: int) -> None:
        ticks = self.sample_wind_poll()
        with self.samples_lock:
            self.samples[sample_id] = ticks
        if self.debug:
            self.log.info(f"Sample {sample_id} has {len(ticks)} ticks")

    def append_pending_wind_data(self, wind_data: dict) -> None:
        with self.pending_wind_data_lock:
            self.pending_wind_data.append(wind_data)

    def calculate_processing_overhead(self) -> None:
        time_now_ms = ticks_ms()
        processing_time_ms = ticks_diff(time_now_ms, self.previous_loop_time_ms)
        self.previous_loop_time_ms = time_now_ms
        self.last_loop_overhead_ms = processing_time_ms - ((self.monitoring_window_s * 1000) - self.last_loop_overhead_ms)
        self.remaining_loop_overhead_ms = self.last_loop_overhead_ms
        self.processing_overhead_poll_count = 0
        if self.debug:
            self.log.info(f"Processing overhead: {self.last_loop_overhead_ms}ms")

    def constant_poll_wind_speed(self) -> None:
        self.previous_loop_time_ms = ticks_ms()
        sample_id = 0
        while True:
            if sample_id % 30 == 0:
                try:
                    from lib.weather import weather
                    if hasattr(weather, 'wifi') and hasattr(weather.wifi, 'pet_watchdog'):
                        weather.wifi.pet_watchdog()
                except Exception:
                    pass
            if self.remaining_loop_overhead_ms > 0:
                self.discard_overhead_compensation_poll()
            else:
                self.record_sample_datapoint(sample_id)
            if sample_id < self.samples_max_list_id:
                sample_id += 1
            else:
                sample_id = 0
                self.append_pending_wind_data(self.process_wind_data())
                self.calculate_processing_overhead()

    def calculate_wind_speed_m_s(self, average_tick_ms: float) -> float:
        if average_tick_ms == 0:
            wind_m_s = 0
        else:
            rotation_hz = (1000 / average_tick_ms) / 2
            circumference = self.WIND_CM_RADIUS * 2.0 * math.pi
            wind_m_s = rotation_hz * circumference * self.WIND_FACTOR
        return wind_m_s

    def calculate_average_wind(self, samples: list) -> float:
        average_tick_ms = self.calculate_sample_set_average_duration_ms(samples)
        average_wind_speed = self.calculate_wind_speed_m_s(average_tick_ms)
        return average_wind_speed

    def calculate_sample_set_average_duration_ms(self, sample_set: list) -> float:
        ticks = []
        for sample in sample_set:
            for tick in sample:
                ticks.append(tick)
        total_sample_set_ticks = len(ticks)
        if total_sample_set_ticks > 1:
            total_sample_set_time = ticks_diff(ticks[-1], ticks[0])
            return total_sample_set_time / total_sample_set_ticks
        return 0

    def determine_gust_wind(self, samples: list) -> float:
        gust_wind_speed = 0
        gust_window_samples = self.gust_rolling_average_duration_s * self.sample_hz
        for start_sample in range(len(samples) - int(gust_window_samples)):
            current_average_duration = self.calculate_sample_set_average_duration_ms(
                samples[start_sample:start_sample + int(gust_window_samples)]
            )
            current_speed = self.calculate_wind_speed_m_s(current_average_duration)
            if current_speed > gust_wind_speed:
                gust_wind_speed = current_speed
        return gust_wind_speed

    def cache_samples(self) -> None:
        with self.samples_lock:
            self.cached_samples = [s.copy() for s in self.samples]

    def remove_processing_overhead_data_polls(self, samples: list) -> list:
        return self.cached_samples[self.processing_overhead_poll_count:]

    def process_wind_data(self) -> dict:
        self.cache_samples()
        samples = self.remove_processing_overhead_data_polls(self.cached_samples)
        gust_wind_error = 0
        gust_wind = self.determine_gust_wind(samples)
        if gust_wind > 50:
            self.log.error(f"Wind speed is too high: {gust_wind}")
            gust_wind_error = gust_wind
            gust_wind = 0
        self.log.info(f"> gust wind speed is: {gust_wind}")
        average_wind = self.calculate_average_wind(samples)
        self.log.info(f"> average wind speed is: {average_wind}")
        result = {
            "timestamp": time(),
            "avg_wind_speed": average_wind,
            "gust_wind_speed": gust_wind,
            "gust_wind_error": gust_wind_error,
            "samples_count": len(samples)
        }
        return result

    def get_pending_data(self) -> list:
        with self.pending_wind_data_lock:
            return [d.copy() for d in self.pending_wind_data]

    def clear_pending_data(self) -> None:
        with self.pending_wind_data_lock:
            self.pending_wind_data = []

    def check_pending_wind_data_length(self) -> int:
        with self.pending_wind_data_lock:
            return len(self.pending_wind_data)


class RainSensor:
    """
    Rain sensor implementation using a tipping bucket mechanism.
    Each tip of the bucket represents a fixed amount of rainfall (RAIN_MM_PER_TICK).
    
    Uses buffered approach:
    - Poll at 4Hz, store tips in memory buffer
    - Write tip count to file every 60 seconds (per minute)
    - rain_mm calculated from buffer (last 60s)
    - rain_per_hour and rain_per_day calculated from file
    - File is cleared at start of new day
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

        # Rain data persistence file - stores tip counts per minute
        self.rain_file = "rain_minutes.txt"

        # Last known state of the rain pin - initialize to current state
        # This prevents false triggers on startup if the bucket is already tipped
        initial_state = self.rain_pin.value()
        self.last_rain_trigger = initial_state
        self.logger.info(f"Rain sensor initial pin state: {initial_state}")

        # In-memory buffer for tips in current minute
        self.tip_buffer = []
        
        # Track current minute to detect minute boundaries
        self.current_minute_timestamp = None
        self.current_day = None

        # For debouncing mechanical switch bounce
        self.last_tip_time_ms = 0
        self.debounce_ms = 20  # Filter out bounce within 20ms

        # Initialize tracking timestamps
        self._update_current_minute()
        
        # Initialize rain log file if it doesn't exist, clear if new day
        self._initialize_rain_file()

    def _file_exists(self, filename: str) -> bool:
        """Check if a file exists."""
        try:
            return os.stat(filename)[0] & 0x4000 == 0
        except OSError:
            return False

    def _update_current_minute(self) -> None:
        """Update current minute and day tracking."""
        dt = gmtime()
        # Format: YYYY-MM-DDTHH:MMZ (minute precision)
        self.current_minute_timestamp = f"{dt[0]:04d}-{dt[1]:02d}-{dt[2]:02d}T{dt[3]:02d}:{dt[4]:02d}Z"
        self.current_day = dt[2]  # Day of month

    def _get_current_minute_timestamp(self) -> str:
        """Get current minute timestamp in ISO format (minute precision)."""
        dt = gmtime()
        return f"{dt[0]:04d}-{dt[1]:02d}-{dt[2]:02d}T{dt[3]:02d}:{dt[4]:02d}Z"

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        dt = gmtime()
        return f"{dt[0]:04d}-{dt[1]:02d}-{dt[2]:02d}T{dt[3]:02d}:{dt[4]:02d}:{dt[5]:02d}Z"

    def _initialize_rain_file(self) -> None:
        """Initialize rain file, clear if new day."""
        current_date = gmtime()
        current_day = current_date[2]  # Day of month
        
        # If file exists but it's a new day, clear it
        if self._file_exists(self.rain_file):
            try:
                # Check if file has data from previous day
                with open(self.rain_file, "r") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        # Extract full date from first entry: YYYY-MM-DDT...
                        # Format: YYYY-MM-DDTHH:MMZ,count
                        file_date_str = first_line.split(",")[0]
                        file_year = int(file_date_str[0:4])
                        file_month = int(file_date_str[5:7])
                        file_day = int(file_date_str[8:10])
                        
                        # Compare full date (year, month, day)
                        if (file_year != current_date[0] or 
                            file_month != current_date[1] or 
                            file_day != current_day):
                            self.logger.info(f"New day detected ({current_date[0]}-{current_date[1]}-{current_day}), clearing rain file")
                            with open(self.rain_file, "w") as f:
                                f.write("")
            except Exception as e:
                self.logger.error(f"Failed to check rain file day: {e}")
        else:
            # Create new file
            self.logger.info("Creating new rain file")
            with open(self.rain_file, "w") as f:
                f.write("")

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
        Detects both LOW->HIGH and HIGH->LOW transitions to handle different sensor types.
        Uses short debounce (20ms) to filter switch bounce but not rapid tips.
        Returns True if a new tip is detected.
        """
        rain_sensor_trigger = self.rain_pin.value()

        # Detect transition in either direction (handles both sensor types)
        if rain_sensor_trigger != self.last_rain_trigger:
            # Check debounce period (only filter very rapid transitions <20ms)
            current_time_ms = ticks_ms()
            time_since_last = ticks_diff(current_time_ms, self.last_tip_time_ms)

            if time_since_last < self.debounce_ms:
                # Too soon - switch bounce, ignore
                self.last_rain_trigger = rain_sensor_trigger
                return False

            self.logger.info(f"Rain bucket tip detected! (pin={rain_sensor_trigger})")
            # Add to in-memory buffer instead of writing to file immediately
            self.tip_buffer.append(current_time_ms)
            self.last_rain_trigger = rain_sensor_trigger
            self.last_tip_time_ms = current_time_ms
            return True

        self.last_rain_trigger = rain_sensor_trigger
        return False

    def get_rainfall_data(self, seconds_since_last: float = 0) -> dict:
        """
        Calculate rainfall data based on buffered tips.
        - rain_mm: from in-memory buffer (last 60s)
        - rain_per_hour: from file (sum of last 60 minutes)
        - rain_per_day: from file (sum of today's minutes)
        
        Also writes current buffer to file and clears buffer.
        Clears file if new day detected.

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
        # Calculate rain_mm and rain_tips from buffer (last 60s)
        rain_mm = len(self.tip_buffer) * RAIN_MM_PER_TICK
        rain_tips = len(self.tip_buffer)
        
        # Check if we need to clear file for new day
        current_date = gmtime()
        current_day = current_date[2]
        file_cleared = False
        if self.current_day != current_day:
            self.logger.info(f"New day detected ({current_date[0]}-{current_date[1]}-{current_day}), clearing rain file")
            try:
                with open(self.rain_file, "w") as f:
                    f.write("")
                self.current_day = current_day
                file_cleared = True
            except Exception as e:
                self.logger.error(f"Failed to clear rain file for new day: {e}")
        
        # Write current buffer to file (if not empty or file was just cleared)
        if len(self.tip_buffer) > 0 or file_cleared:
            minute_timestamp = self._get_current_minute_timestamp()
            tip_count = len(self.tip_buffer)
            try:
                with open(self.rain_file, "a") as f:
                    f.write(f"{minute_timestamp},{tip_count}\n")
                self.logger.info(f"Wrote {tip_count} tips for {minute_timestamp} to file")
            except Exception as e:
                self.logger.error(f"Failed to write rain minute to file: {e}")
        
        # Clear buffer for next cycle
        self.tip_buffer = []
        self._update_current_minute()
        
        # Calculate rain_per_hour and rain_per_day from file
        rain_per_hour = self._calculate_from_file(3600)  # Last hour
        rain_per_day = self._calculate_from_file(86400)   # Last 24 hours

        return {
            'rain_mm': round(rain_mm, 3),
            'rain_per_hour': round(rain_per_hour, 3),
            'rain_per_day': round(rain_per_day, 3),
            'rain_tips': rain_tips
        }
    
    def _calculate_from_file(self, seconds: int) -> float:
        """
        Calculate total rainfall from file entries within time window.
        
        Args:
            seconds: Time window in seconds (3600 for hour, 86400 for day)
            
        Returns:
            Total rainfall in mm
        """
        if not self._file_exists(self.rain_file):
            return 0.0
        
        current_time = time()
        total_mm = 0.0
        
        try:
            with open(self.rain_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse: YYYY-MM-DDTHH:MMZ,count
                    parts = line.split(",")
                    if len(parts) != 2:
                        self.logger.warning(f"Invalid rain file entry: {line}")
                        continue
                    
                    timestamp_str = parts[0]
                    try:
                        tip_count = int(parts[1])
                    except ValueError:
                        self.logger.warning(f"Invalid tip count in rain file: {parts[1]}")
                        continue
                    
                    # Convert minute timestamp to epoch
                    # Format: YYYY-MM-DDTHH:MMZ
                    try:
                        year = int(timestamp_str[0:4])
                        month = int(timestamp_str[5:7])
                        day = int(timestamp_str[8:10])
                        hour = int(timestamp_str[11:13])
                        minute = int(timestamp_str[14:16])
                        
                        from time import mktime
                        entry_time = mktime((year, month, day, hour, minute, 0, 0, 0, 0))
                        
                        # Check if within time window
                        if current_time - entry_time < seconds:
                            total_mm += tip_count * RAIN_MM_PER_TICK
                    except Exception as e:
                        self.logger.warning(f"Failed to parse timestamp {timestamp_str}: {e}")
                        continue
        except Exception as e:
            self.logger.error(f"Failed to read rain file for calculation: {e}")
        
        return total_mm

    async def async_poll_rain(self, poll_frequency_s: float) -> None:
        """
        Async polling for rain sensor at 4Hz (250ms intervals).
        Checks for bucket tips and stores in memory buffer.
        File write happens in get_rainfall_data() every 60s.
        Does NOT add to weather_data - that's done by get_all_readings() in combined polling.
        """
        while True:
            try:
                # Check for immediate rain triggers
                self.check_rain_trigger()
            except Exception as e:
                self.logger.error(f"Failed in rain polling: {e}")

            await sleep(0.25)  # Check 4 times per second (MET office compliant)




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

        # MET standard: 3-second window for gust, 2-second window for average wind speed
        self.wind_speed_window_seconds = 2.0  # Window for average wind speed calculation

        # For storing wind speed samples (calculated values)
        self.speed_samples = []

        # For storing raw tick timestamps (reed switch transitions)
        # This allows non-blocking 4Hz polling with proper sample windows
        self.tick_timestamps = []  # List of timestamp_ms values
        self.max_tick_history = 100  # Keep last 100 ticks to prevent memory bloat

        # Calculate max_samples based on polling frequency: 60 seconds of data
        self.max_samples = max(1, int(60 / WIND_SPEED_POLL_FREQUENCY)) if WIND_SPEED_POLL_FREQUENCY > 0 else 240

        # For gust calculation: track average of each window
        self.window_duration = WIND_GUST_WINDOW_SECONDS
        self.window_avg_values = []  # Stores average value of each window
        self.current_window_samples = []  # Samples in current window
        self.window_start_time = 0  # Start time of current window

        # Track previous pin state for detecting transitions
        self._last_pin_state = self.wind_speed_pin.value()
        self._last_poll_time_ms = ticks_ms()

    def _check_and_record_ticks(self) -> None:
        """
        Non-blocking check for pin state changes.
        Records timestamps of all transitions since last check.
        Must be called frequently (e.g., at poll frequency).
        """
        current_state = self.wind_speed_pin.value()
        current_time_ms = ticks_ms()

        # If state changed, record the transition
        if current_state != self._last_pin_state:
            # Record the timestamp of this transition
            self.tick_timestamps.append(current_time_ms)
            self._last_pin_state = current_state

            # Clean up old timestamps (older than 10 seconds)
            cleanup_threshold = current_time_ms - 10000
            self.tick_timestamps = [t for t in self.tick_timestamps if t > cleanup_threshold]

            # Limit history size
            if len(self.tick_timestamps) > self.max_tick_history:
                self.tick_timestamps = self.tick_timestamps[-self.max_tick_history:]

    def measure_wind_speed(self, sample_time_ms: int = 2000) -> float:
        """
        Measure wind speed from accumulated tick timestamps.
        
        Uses ticks collected via _check_and_record_ticks() over the specified
        sample window. This is non-blocking and allows true 4Hz MET standard measurement.

        Args:
            sample_time_ms: Sample window in milliseconds (default: 2000ms = 2 seconds)

        Returns:
            float: Wind speed in meters per second
        """
        current_time_ms = ticks_ms()

        # Filter ticks within the sample window
        window_start = current_time_ms - sample_time_ms
        ticks_in_window = [t for t in self.tick_timestamps if t >= window_start]

        # Need at least 2 ticks to calculate speed
        if len(ticks_in_window) < 2:
            return 0.0

        # Calculate average tick time in milliseconds
        average_tick_ms = ticks_diff(ticks_in_window[-1], ticks_in_window[0]) / (len(ticks_in_window) - 1)

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
        Get current wind speed reading and update window tracking.
        Non-blocking: uses pre-recorded tick timestamps.

        Returns:
            dict: {
                'wind_speed': current wind speed in m/s,
                'wind_speed_avg': average wind speed over all samples in period,
                'wind_gust': maximum wind speed over gust window
            }
        """
        # First, check and record any new ticks since last poll
        self._check_and_record_ticks()
        
        # Calculate current speed from accumulated ticks (2-second window per MET standard)
        sample_time_ms = int(self.wind_speed_window_seconds * 1000)
        current_speed = self.measure_wind_speed(sample_time_ms)
        current_time = time()

        # Initialize window tracking on first call
        if self.window_start_time == 0:
            self.window_start_time = current_time

        # Check if we've moved to a new 3-second window (for gust calculation)
        elapsed_in_window = current_time - self.window_start_time
        if elapsed_in_window >= self.window_duration:
            # Save average of completed window and start new window
            if self.current_window_samples:
                window_avg = sum(self.current_window_samples) / len(self.current_window_samples)
                self.window_avg_values.append(window_avg)
                # Limit to windows that fit in 60 seconds
                max_windows = max(1, int(60 / self.window_duration)) if self.window_duration > 0 else 20
                if len(self.window_avg_values) > max_windows:
                    self.window_avg_values = self.window_avg_values[-max_windows:]

            # Start new window
            self.current_window_samples = [current_speed]
            self.window_start_time = current_time
        else:
            # Add to current window
            self.current_window_samples.append(current_speed)

        # Update overall sample history
        self.speed_samples.append(current_speed)
        if len(self.speed_samples) > self.max_samples:
            self.speed_samples = self.speed_samples[-self.max_samples:]

        # Calculate average from all samples in the current period
        if self.speed_samples:
            avg_speed = round(sum(self.speed_samples) / len(self.speed_samples), 2)
        else:
            avg_speed = 0.0

        # Calculate gust as max of all 3-second window averages
        if self.window_avg_values:
            gust_speed = round(max(self.window_avg_values), 2)
        else:
            gust_speed = round(current_speed, 2)

        return {
            'wind_speed': round(current_speed, 2),
            'wind_speed_avg': avg_speed,
            'wind_gust': gust_speed
        }

    async def async_poll_wind_speed(self, poll_frequency_s: int) -> None:
        """
        Async polling for wind speed sensor.
        Measures wind speed at the specified frequency and updates internal samples.
        Does NOT add to weather_data - that's done by async_poll_wind_speed_for_upload.
        """
        while True:
            try:
                # Just measure and update internal state, don't publish yet
                self.get_current_wind_speed()
            except Exception as e:
                self.logger.error(f"Failed in wind speed polling: {e}")

            await sleep(poll_frequency_s)




class WindDirectionSensor:
    """
    Wind direction sensor implementation using an analog potentiometer.
    Converts analog voltage to wind direction in degrees.
    
    Uses 8-direction mapping based on calibration data:
    - N:  1.85-2.15V -> 0°
    - NE: 1.00-1.45V -> 45°
    - E:  0.00-0.45V -> 90°
    - SE: 0.45-0.70V -> 135°
    - S:  0.70-1.00V -> 180°
    - SW: 1.45-1.85V -> 225°
    - W:  2.50-3.30V -> 270°
    - NW: 2.15-2.50V -> 315°
    """

    # Voltage ranges for 8 cardinal directions
    # Format: (min_voltage, max_voltage, degrees)
    VOLTAGE_TO_DIRECTION_8 = (
        (0.00, 0.45, 90.0),   # E
        (0.45, 0.70, 135.0),  # SE
        (0.70, 1.00, 180.0),  # S
        (1.00, 1.45, 45.0),   # NE
        (1.45, 1.85, 225.0),  # SW
        (1.85, 2.15, 0.0),    # N
        (2.15, 2.50, 315.0),  # NW
        (2.50, 3.30, 270.0),  # W
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

        # Store latest reading for upload
        self.current_direction = 0.0

        # For mode calculation - store all readings over the period
        self.direction_samples = []
        self.max_direction_samples = 240  # Store ~240 readings at 0.25s intervals over 60s (4Hz)

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
        Uses 8-direction mapping based on calibrated voltage ranges.

        Returns:
            float: Wind direction in degrees, adjusted by offset
        """
        voltage = self.read_voltage()

        # Find direction based on voltage range
        for min_volt, max_volt, degrees in self.VOLTAGE_TO_DIRECTION_8:
            if min_volt <= voltage < max_volt:
                # Apply offset and ensure it's within 0-360 range
                adjusted_direction = (degrees + self.direction_offset) % 360
                return round(adjusted_direction, 1)

        # Fallback: if voltage is out of all ranges (shouldn't happen), return N with offset
        self.logger.warning(f"Voltage {voltage:.3f}V outside all ranges, defaulting to N")
        adjusted_direction = (0.0 + self.direction_offset) % 360
        return round(adjusted_direction, 1)

    async def async_poll_wind_direction(self, poll_frequency_s: int) -> None:
        """
        Async polling for wind direction sensor.
        Reads wind direction at the specified frequency and stores samples.
        Does NOT add to weather_data - that's done by get_all_readings() in combined polling.
        """
        while True:
            try:
                direction = self.get_wind_direction()
                self.current_direction = direction
                # Store for mode calculation
                self.direction_samples.append(direction)
                if len(self.direction_samples) > self.max_direction_samples:
                    self.direction_samples = self.direction_samples[-self.max_direction_samples:]
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
        # Use MulticoreWindSpeedSensor for accurate wind speed measurement
        self.wind_speed_sensor = MulticoreWindSpeedSensor() if ENABLE_WIND_SENSORS else None
        self.wind_direction_sensor = WindDirectionSensor() if ENABLE_WIND_SENSORS else None

        # Store latest readings for combined publishing
        self.latest_readings = {}

        if not ENABLE_RAIN_SENSOR:
            self.logger.info("Rain sensor disabled via config")
        if not ENABLE_WIND_SENSORS:
            self.logger.info("Wind sensors disabled via config")
        else:
            self.logger.info("Using MulticoreWindSpeedSensor for accurate wind speed measurement")

    async def async_poll_all(self) -> None:
        """
        Start async polling for all wind and rain sensors.
        Each sensor can have its own polling frequency.
        """
        # Start individual sensor polling tasks
        from asyncio import create_task

        if ENABLE_RAIN_SENSOR and self.rain_sensor:
            # Poll rain sensor at 4Hz (250ms) - updates internal buffer only
            create_task(self.rain_sensor.async_poll_rain(0.25))

        # Wind speed is now handled by MulticoreWindSpeedSensor thread (Core 2)
        # No async polling needed - see WeatherStation.startup() for thread initialization

        if ENABLE_WIND_SENSORS and self.wind_direction_sensor:
            # Fast polling for measurement (5 seconds) - updates internal state only
            create_task(self.wind_direction_sensor.async_poll_wind_direction(WIND_DIRECTION_POLL_FREQUENCY))

    def get_all_readings(self) -> dict:
        """
        Get current readings from all wind and rain sensors.
        Uses stored state from async measurement tasks, does NOT take new measurements.
        Useful for manual polling or testing.
        """
        readings = {}

        # Rain data - use stored state from async tasks
        if ENABLE_RAIN_SENSOR and self.rain_sensor:
            # Calculate from file (includes all tips since last report)
            rain_data = self.rain_sensor.get_rainfall_data(60)  # Last 60 seconds
            readings.update(rain_data)

        # Wind speed data - from multicore thread
        if ENABLE_WIND_SENSORS and self.wind_speed_sensor:
            # Check if we have pending data from the multicore wind sensor
            if hasattr(self.wind_speed_sensor, 'check_pending_wind_data_length'):
                pending_count = self.wind_speed_sensor.check_pending_wind_data_length()
                if pending_count > 0:
                    # Get the most recent wind data
                    pending_data = self.wind_speed_sensor.get_pending_data()
                    if pending_data:
                        latest_wind = pending_data[-1]
                        # Extract wind data from multicore sensor
                        avg_wind_speed = latest_wind.get('avg_wind_speed', 0.0)
                        gust_wind_speed = latest_wind.get('gust_wind_speed', 0.0)
                        
                        readings.update({
                            'wind_speed': round(avg_wind_speed, 2),
                            'wind_speed_avg': round(avg_wind_speed, 2),
                            'wind_gust': round(gust_wind_speed, 2)
                        })
                        
                        # Clear the pending data after reading
                        self.wind_speed_sensor.clear_pending_data()
                    else:
                        readings.update({
                            'wind_speed': 0.0,
                            'wind_speed_avg': 0.0,
                            'wind_gust': 0.0
                        })
                else:
                    # No pending data yet, return zeros
                    readings.update({
                        'wind_speed': 0.0,
                        'wind_speed_avg': 0.0,
                        'wind_gust': 0.0
                    })
            else:
                # Fallback to zeros if method doesn't exist
                readings.update({
                    'wind_speed': 0.0,
                    'wind_speed_avg': 0.0,
                    'wind_gust': 0.0
                })

        # Wind direction data - use mode (most frequent) from async tasks
        if ENABLE_WIND_SENSORS and self.wind_direction_sensor:
            if self.wind_direction_sensor.direction_samples:
                # Calculate mode (most frequent direction) manually
                # Since wind direction is in 22.5° increments (0, 22.5, 45, ..., 337.5)
                # we can use a simple frequency dictionary
                freq = {}
                max_count = 0
                most_common = self.wind_direction_sensor.current_direction
                for direction in self.wind_direction_sensor.direction_samples:
                    count = freq.get(direction, 0) + 1
                    freq[direction] = count
                    if count > max_count:
                        max_count = count
                        most_common = direction
                readings['wind_direction'] = most_common
                total_samples = len(self.wind_direction_sensor.direction_samples)
                self.logger.info(f"Wind direction mode: {most_common}° ({max_count} out of {total_samples} samples)")
                # Clear samples after reporting
                self.wind_direction_sensor.direction_samples = []
            else:
                readings['wind_direction'] = self.wind_direction_sensor.current_direction

        return readings
