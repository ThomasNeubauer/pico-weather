from gc import mem_free
from os import stat, remove, rename
from time import gmtime, time

class uLogger:
    
    def __init__(self, module_name: str, log_level: int = 0, handlers: list = []) -> None:
        """
        Init with module name to log and session debug level, that defaults to 2 and can be overidden globally using log_level=x in config.py
        Raise a debug message using the appropriate function for the severity
        Debug level 0-3: Each level adds more verbosity
        0 = Disabled, 1 = Critical, 2 = Error, 3 = Warning, 4 = Info
        """
        self.module_name = module_name
        self.configure_log_level(log_level)
        self.configure_handlers(handlers)

    def configure_log_level(self, log_level: int) -> None:
        self.log_level = 0
        
        if log_level > 0:
            self.log_level = log_level
        else:
            try:
                from config import LOG_LEVEL as config_log_level
                self.log_level = config_log_level
            except ImportError:
                print("LOG_LEVEL not found in config.py not found. Using default log level.")
            except Exception as e:
                print(f"An unexpected error occurred: {e}. Using default log level.")

    def configure_handlers(self, handlers: list) -> None:
        self.handlers = []
        self.handler_objects = []
        
        if len(handlers) > 0:
            self.handlers = handlers
        else:
            try:
                from config import LOG_HANDLERS as config_log_handlers
                self.handlers = config_log_handlers
            except ImportError:
                print("LOG_HANDLERS not found in config.py not found. Using default output handler.")
            except Exception as e:
                print(f"An unexpected error occurred: {e}. Using default output handler.")
        
        for handler in self.handlers:
            try:
                handler_class = globals().get(handler)
                
                if handler_class is None:
                    raise ValueError(f"Handler class '{handler}' not found.")
                
                handler = handler_class()
                self.handler_objects.append(handler)
            except Exception as e:
                print(f"An error occurred while confguring handler '{handler}': {e}")
                raise

    def decorate_message(self, message: str, level: str) -> str:
        time_str = gmtime(time())
        timestamp = f"{time_str[0]}-{time_str[1]}-{time_str[2]} {time_str[3]}:{time_str[4]}:{time_str[5]}"
        decorated_message = f"[{timestamp}][Mem: {round(mem_free() / 1024)}kB free][{level}][{self.module_name}]: {message}"
        return decorated_message
    
    def process_handlers(self, message: str) -> None:
        for handler in self.handler_objects:
            try:
                handler.emit(message)
            except Exception as e:
                print(f"An error occurred while processing handler '{handler}': {e}")
                raise
    
    def info(self, message: str) -> None:
        if self.log_level > 3:
            self.process_handlers(self.decorate_message(message, "Info"))

    def warn(self, message: str) -> None:
        if self.log_level > 2:
            self.process_handlers(self.decorate_message(message, "Warning"))

    def error(self, message: str) -> None:
        if self.log_level > 1:
            self.process_handlers(self.decorate_message(message, "Error"))

    def critical(self, message: str) -> None:
        if self.log_level > 0:
            self.process_handlers(self.decorate_message(message, "Critical"))

class Console:
    def __init__(self) -> None:
        pass
    
    def emit(self, message) -> None:
        print(message)

class File:
    def __init__(self) -> None:
        self.log_file = "log.txt"
        self.second_log_file = "log2.txt"
        from config import LOG_FILE_MAX_SIZE
        self.LOG_FILE_MAX_SIZE = LOG_FILE_MAX_SIZE
        self.LOG_MAX_AGE_SECONDS = 86400  # 24 hours
    
    def _parse_timestamp_from_line(self, line: str):
        """Extract epoch timestamp from log line format: [2026-10-02 13:26:37]..."""
        try:
            if line.startswith('['):
                # Format: [2026-10-2 13:26:37][Mem: ...][...]...
                # Extract date and time part
                first_bracket = line.find(']')
                if first_bracket > 0:
                    ts_str = line[1:first_bracket]  # "2026-10-2 13:26:37"
                    parts = ts_str.split()
                    if len(parts) >= 2:
                        date_part = parts[0]  # "2026-10-2"
                        time_part = parts[1]  # "13:26:37"
                        year = int(date_part[0:4])
                        month = int(date_part[5:7])
                        day = int(date_part[8:10])
                        hour = int(time_part[0:2])
                        minute = int(time_part[3:5])
                        second = int(time_part[6:8])
                        from time import mktime
                        return mktime((year, month, day, hour, minute, second, 0, 0, 0))
        except:
            pass
        return 0
    
    def _file_exists(self, filepath: str) -> bool:
        """Check if file exists (MicroPython compatible)"""
        try:
            stat(filepath)
            return True
        except OSError:
            return False
    
    def _trim_old_entries(self) -> None:
        """Remove log entries older than LOG_MAX_AGE_SECONDS (24 hours)"""
        if not self._file_exists(self.log_file):
            return
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
            
            cutoff_time = time() - self.LOG_MAX_AGE_SECONDS
            recent_lines = []
            
            for line in lines:
                line_time = self._parse_timestamp_from_line(line)
                if line_time >= cutoff_time:
                    recent_lines.append(line)
            
            with open(self.log_file, "w") as f:
                f.writelines(recent_lines)
        except:
            pass
    
    def emit(self, message) -> None:
        with open(self.log_file, "a") as log_file:
            log_file.write(message + "\n")
        self.check_for_rotate()

    def check_for_rotate(self) -> None:
        log_file_size = stat(self.log_file)[6]
        if log_file_size > self.LOG_FILE_MAX_SIZE:
            self._trim_old_entries()  # Trim before rotating
            self.rotate_file()

    def rotate_file(self) -> None:
        try:
            remove(self.second_log_file)
        except OSError:
            print(f"{self.second_log_file} did not exist to be deleted.")
        
        rename(self.log_file, self.second_log_file)
    