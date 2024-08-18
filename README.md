# Pico Weather
## Overview
Pico based weather station inspired by the [Pimoroni-enviro weather board.](https://github.com/pimoroni/enviro)

The Pimoroni Enviro solution was aimed at using the Pico W to power a number of different environment monitoring solutions (including a weather station), with a focus on low powered devices making infrequent readings with a low power sleep state so they could last months on one set of batteries.

I encountered issues with the board occasionally crashing, which I can only assume is related to the fancy RTC wake board from sleep circuitry, as the code seems to be error free.

I also wanted something slightly different in that I was willing to power the unit permanently and improve measurement precision and improve destination flexibility as wifi power use was no longer a concern. As my [fork](https://github.com/sjefferson99/enviro) was departing too far from the Pimoroni Enviro intended approach, I am recreating the concepts in that repo in a new implementation here.

## Target improvements
- Doesn't crash
- Reduce reliance and use of the flash filesystem to only be needed on upload failures
- Improve poll frequency of the wind speed and direction to 4 times a second to match the MET office approach for average and gust wind speed recordings
- Add weather underground as a potential destination
- Adjust pressure to sea level to match MET office expectations
- Add rain per hour and day to meet Wunderground API requirements
- Support multiple destinations, so extra or debug data can be sent to InfluxDB while still logging to Wunderground
- Move BME280 off the main board that was dissipating heat from the pico processor and power regulator to improve temperature accuracy
- Move to fully async code

## What works so far
- Doesn't crash
- Filesystem only used to cache failed uploads
- Fully async
- BME280 offboard (There is no board yet) and polling readings
- InfluxDB destination
- Sea level pressure compensation
- Configurable multiple destinations

## Development
### Firmware
Pico W code built against firmware: [Pimoroni v1.23.0 - pico-w](https://github.com/pimoroni/pimoroni-pico/releases/tag/v1.23.0-1)
