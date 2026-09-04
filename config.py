## Logging
# Level 0-4: 0 = Disabled, 1 = Critical, 2 = Error, 3 = Warning, 4 = Info
LOG_LEVEL = 2
# Handlers: Populate list with zero or more of the following log output handlers (case sensitive): "Console", "File"
LOG_HANDLERS = ["Console", "File"]
# Max log file size in bytes, there will be a maximum of 2 files at this size created
LOG_FILE_MAX_SIZE = 10240

## WIFI
# WIFI_SSID = 'flaptrack'
# WIFI_PASSWORD = 'fp2026ems'
WIFI_SSID = "A1-E6AB7E31"
WIFI_PASSWORD = "WA4NOfEaZ7Y1DU"
WIFI_COUNTRY = "GB"
WIFI_CONNECT_TIMEOUT_SECONDS = 10
WIFI_CONNECT_RETRIES = 1
WIFI_RETRY_BACKOFF_SECONDS = 5
# Leave as none for MAC based unique hostname or specify a custom hostname string
CUSTOM_HOSTNAME = "Pico-Weather"
# Upload frequency management
UPLOAD_RETRY_SECONDS = 30
MAX_UPLOADS_PER_MIN = 10

NTP_SYNC_INTERVAL_SECONDS = 86400

# I2C pins - configure based on your board
# Pimoroni Enviro boards: sda=4, scl=5
# Generic Pico boards: sda=0, scl=1 (default)
I2C_PINS = {"sda": 4, "scl": 5}

# Influxdb settings
INFLUXDB_ORG = ""
INFLUXDB_URL = ""
INFLUXDB_TOKEN = ""
INFLUXDB_BUCKET = ""
INFLUXDB_DEVICE = CUSTOM_HOSTNAME

# Weather underground settings
WUNDERGROUND_STATION_ID = None
WUNDERGROUND_STATION_KEY = None

# Height in metres above sea level for atmospheric pressure compensation
HEIGHT_ABOVE_SEA_LEVEL_M = 353 # for Graz

# MQTT settings
# MQTT_BROKER_ADDRESS = "10.11.12.108"
MQTT_BROKER_ADDRESS = "10.0.0.5"
MQTT_BROKER_USERNAME = "thomas"
MQTT_BROKER_PASSWORD = "admin"
# MQTT broker CA file for SSL (set to None for non-SSL connections)
MQTT_BROKER_CA_FILE = None
# MQTT topic prefix (default: pico-weather)
MQTT_TOPIC_PREFIX = None

# BME280
BME280_POLL_FREQUENCY = 60

# Temperature offset compensation
# The BME280 sensor can be affected by heat from the board when USB powered
# Set this value to subtract from all temperature readings (degrees Celsius)
TEMPERATURE_OFFSET = 4.5  # Degrees C to subtract from temperature readings

# Destination selection: Add one or more of the following to the list: "InfluxDB", "Example", "MQTT"
DESTINATIONS = ["MQTT"]
