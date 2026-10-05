# Global state for safe time fallback
_last_valid_timestamp = None


def safe_time():
    """
    Returns current time, or falls back to last valid time if system clock is corrupted.
    This ensures measurements continue even when system time is invalid.
    Measurement timing (ticks_ms) remains accurate regardless of system time.
    Receivers can detect and correct bad timestamps.
    """
    global _last_valid_timestamp
    from time import time, gmtime
    
    current = time()
    try:
        year = gmtime(current)[0]
    except:
        year = 0
    
    # Validate: reasonable year range (2020-2030)
    if 2020 <= year <= 2030:
        _last_valid_timestamp = current
        return current
    
    # System time is corrupted - use last valid timestamp
    if _last_valid_timestamp is not None:
        return _last_valid_timestamp
    
    # No valid timestamp yet - use epoch (0) as fallback
    # Receiver will detect and correct this
    return 0


# Global state for safe gmtime fallback
_last_valid_gmtime = None


def safe_gmtime():
    """
    Returns current time as struct_time, or falls back to last valid gmtime if system clock is corrupted.
    This ensures consistent timestamp formatting even when system time is invalid.
    """
    global _last_valid_gmtime
    from time import gmtime
    
    # Try to get current time and validate it
    try:
        current = safe_time()
        if current > 0:
            result = gmtime(current)
            _last_valid_gmtime = result
            return result
    except:
        pass
    
    # Fall back to last valid gmtime
    if _last_valid_gmtime is not None:
        return _last_valid_gmtime
    
    # No valid gmtime yet - return epoch struct_time
    return (2021, 1, 1, 0, 0, 0, 0, 0, 0)  # 2021-01-01 00:00:00


# Calculates mean sea level pressure (QNH) from observed pressure
# https://keisan.casio.com/exec/system/1224575267
def get_sea_level_pressure(observed_pressure, temperature_in_c, altitude_in_m):
# def sea(pressure, temperature, height):
	qnh = observed_pressure * ((1 - ((0.0065 * altitude_in_m) / (temperature_in_c + (0.0065 * altitude_in_m) + 273.15)))** -5.257)
	return qnh