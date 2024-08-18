"""
Built against firmware: [Pimoroni v1.23.0 - pico-w](https://github.com/pimoroni/pimoroni-pico/releases/tag/v1.23.0-1)
"""

from lib.weather import WeatherStation

weather = WeatherStation()
weather.startup()
