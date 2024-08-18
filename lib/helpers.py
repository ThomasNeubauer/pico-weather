# Calculates mean sea level pressure (QNH) from observed pressure
# https://keisan.casio.com/exec/system/1224575267
def get_sea_level_pressure(observed_pressure, temperature_in_c, altitude_in_m):
# def sea(pressure, temperature, height):
	qnh = observed_pressure * ((1 - ((0.0065 * altitude_in_m) / (temperature_in_c + (0.0065 * altitude_in_m) + 273.15)))** -5.257)
	return qnh