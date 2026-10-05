"""
Built against firmware: [Pimoroni v1.25.0 - pico-w](https://github.com/pimoroni/pimoroni-pico/releases/tag/v1.25.0)
"""

from lib.weather import WeatherStation

weather = WeatherStation()
weather.startup()
