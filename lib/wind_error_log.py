"""
Wind/Multicore-specific error logging mechanism for MicroPython.
Completely self-contained, no type hints, compatible with Pico MicroPython.
"""

import os
import json
from time import time, gmtime


class WindErrorLogger:
    """
    Lightweight error logger specifically for wind and multicore operations.
    Designed for MicroPython on Raspberry Pi Pico.
    """
    
    def __init__(self, module_name="WindMulticore"):
        self.module_name = module_name
        self.log_file = "wind_errors.txt"
        self.backup_file = "wind_errors.bak"
        self.max_file_size = 2048  # 2KB max
        self.max_entries = 50
        self.error_buffer = []
        
        self.thread_health = {
            "last_heartbeat": 0,
            "thread_alive": True,
            "last_error_time": 0,
            "error_count": 0,
            "startup_time": time()
        }
    
    def _get_timestamp(self):
        dt = gmtime()
        return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(
            dt[0], dt[1], dt[2], dt[3], dt[4], dt[5]
        )
    
    def _format_message(self, level, message, data=None):
        timestamp = self._get_timestamp()
        base_msg = "[{}][{}][{}]: {}".format(timestamp, level, self.module_name, message)
        if data:
            try:
                base_msg += " | {}".format(json.dumps(data, separators=(",", ":")))
            except:
                base_msg += " | {}".format(data)
        return base_msg
    
    def _parse_timestamp_from_line(self, line: str):
        """Extract epoch timestamp from log line format: [2026-10-02T13:26:37Z]..."""
        try:
            if line.startswith('['):
                # Extract timestamp between [ and ]
                end_bracket = line.find(']')
                if end_bracket > 1:
                    ts_str = line[1:end_bracket]  # "2026-10-02T13:26:37Z"
                    # Remove trailing Z if present
                    if ts_str.endswith('Z'):
                        ts_str = ts_str[:-1]
                    # Parse: YYYY-MM-DDTHH:MM:SS
                    year = int(ts_str[0:4])
                    month = int(ts_str[5:7])
                    day = int(ts_str[8:10])
                    hour = int(ts_str[11:13])
                    minute = int(ts_str[14:16])
                    second = int(ts_str[17:19])
                    from time import mktime
                    return mktime((year, month, day, hour, minute, second, 0, 0, 0))
        except:
            pass
        return 0
    
    def _file_exists(self, filepath: str) -> bool:
        """Check if file exists (MicroPython compatible)"""
        try:
            os.stat(filepath)
            return True
        except OSError:
            return False
    
    def _trim_old_errors(self, max_age_seconds: int = 86400):
        """Remove log entries older than max_age_seconds (default: 24 hours)"""
        if not self._file_exists(self.log_file):
            return
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
            
            cutoff_time = time() - max_age_seconds
            recent_lines = []
            
            for line in lines:
                line_time = self._parse_timestamp_from_line(line)
                if line_time >= cutoff_time:
                    recent_lines.append(line)
            
            # Write back only recent entries
            with open(self.log_file, "w") as f:
                f.writelines(recent_lines)
        except:
            pass
    
    def _rotate_log_file(self):
        try:
            if self._file_exists(self.log_file):
                file_size = os.stat(self.log_file)[6]
                if file_size > self.max_file_size:
                    if self._file_exists(self.backup_file):
                        try:
                            os.remove(self.backup_file)
                        except OSError:
                            pass
                    os.rename(self.log_file, self.backup_file)
        except:
            pass
    
    def _write_to_file(self, message):
        self._rotate_log_file()
        self._trim_old_errors()  # Trim old entries after rotation
        try:
            with open(self.log_file, "a") as f:
                f.write(message + "\n")
        except:
            pass
    
    def log_error(self, message, data=None):
        formatted = self._format_message("ERROR", message, data)
        self.error_buffer.append(("ERROR", formatted, time()))
        self.thread_health["last_error_time"] = time()
        self.thread_health["error_count"] += 1
        self._write_to_file(formatted)
        if len(self.error_buffer) > self.max_entries:
            self.error_buffer = self.error_buffer[-self.max_entries:]
    
    def log_warning(self, message, data=None):
        formatted = self._format_message("WARNING", message, data)
        self.error_buffer.append(("WARNING", formatted, time()))
        if len(self.error_buffer) > self.max_entries:
            self.error_buffer = self.error_buffer[-self.max_entries:]
    
    def update_heartbeat(self):
        self.thread_health["last_heartbeat"] = time()
        self.thread_health["thread_alive"] = True
    
    def mark_thread_dead(self):
        self.thread_health["thread_alive"] = False
        self.thread_health["last_error_time"] = time()
        self.log_error("Thread marked as dead")
    
    def mark_thread_crash(self, error):
        self.thread_health["thread_alive"] = False
        self.thread_health["last_error_time"] = time()
        self.thread_health["error_count"] += 1
        self.log_error("Thread crashed: {}".format(error))
    
    def get_thread_health(self):
        return {
            "alive": self.thread_health["thread_alive"],
            "last_heartbeat": self.thread_health["last_heartbeat"],
            "last_error_time": self.thread_health["last_error_time"],
            "error_count": self.thread_health["error_count"],
            "uptime_seconds": time() - self.thread_health["startup_time"]
        }
    
    def get_recent_errors(self, count=10):
        errors = []
        for level, message, timestamp in self.error_buffer[-count:]:
            if level in ("ERROR", "WARNING"):
                errors.append({
                    "timestamp": timestamp,
                    "level": level,
                    "message": message
                })
        return errors
    
    def read_error_log(self):
        entries = []
        if not self._file_exists(self.log_file):
            return entries
        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(line)
        except:
            pass
        return entries
    
    def clear_error_log(self):
        try:
            if self._file_exists(self.log_file):
                os.remove(self.log_file)
            if self._file_exists(self.backup_file):
                os.remove(self.backup_file)
        except:
            pass
        self.error_buffer = []
    
    def enable_debug(self, enable=True):
        self._debug_mode = enable


# Global wind error logger instance
wind_error_logger = WindErrorLogger()


def get_wind_error_logger():
    return wind_error_logger


def log_wind_error(message, data=None):
    wind_error_logger.log_error(message, data)


def log_wind_warning(message, data=None):
    wind_error_logger.log_warning(message, data)


def update_wind_heartbeat():
    wind_error_logger.update_heartbeat()


def mark_wind_thread_crash(error):
    wind_error_logger.mark_thread_crash(error)


def get_wind_thread_health():
    return wind_error_logger.get_thread_health()


def read_wind_error_log():
    return wind_error_logger.read_error_log()


def clear_wind_error_log():
    wind_error_logger.clear_error_log()


def get_wind_error_summary():
    return {
        "health": get_wind_thread_health(),
        "recent_errors": wind_error_logger.get_recent_errors(10),
        "error_log": read_wind_error_log(),
        "error_count": wind_error_logger.thread_health["error_count"]
    }
