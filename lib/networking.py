from utime import ticks_ms, gmtime, time
from math import ceil
import rp2
import network
from ubinascii import hexlify
import config
from lib.ulogging import uLogger
from lib.utils import StatusLED
from asyncio import sleep, create_task
from lib.error_handling import ErrorHandler
from machine import RTC
from socket import getaddrinfo, socket, AF_INET, SOCK_DGRAM
import struct

class WirelessNetwork:

    def __init__(self) -> None:
        self.log = uLogger("WIFI")
        self.log.info("> Initializing Wireless Network...")
        self.status_led = StatusLED()
        self.wifi_ssid = config.WIFI_SSID
        self.wifi_password = config.WIFI_PASSWORD
        self.wifi_country = config.WIFI_COUNTRY
        rp2.country(self.wifi_country)
        self.disable_power_management = 0xa11140
        self.led_retry_backoff_frequency = 4
        self.ntp_sync_interval_seconds = 86400
        if hasattr(config, "NTP_SYNC_INTERVAL_SECONDS"):
            self.ntp_sync_interval_seconds = config.NTP_SYNC_INTERVAL_SECONDS
        
        # Reference: https://datasheets.raspberrypi.com/picow/connecting-to-the-internet-with-pico-w.pdf
        self.CYW43_LINK_DOWN = 0
        self.CYW43_LINK_JOIN = 1
        self.CYW43_LINK_NOIP = 2
        self.CYW43_LINK_UP = 3
        self.CYW43_LINK_FAIL = -1
        self.CYW43_LINK_NONET = -2
        self.CYW43_LINK_BADAUTH = -3
        self.status_names = {
        self.CYW43_LINK_DOWN: "Link is down",
        self.CYW43_LINK_JOIN: "Connected to wifi",
        self.CYW43_LINK_NOIP: "Connected to wifi, but no IP address",
        self.CYW43_LINK_UP: "Connect to wifi with an IP address",
        self.CYW43_LINK_FAIL: "Connection failed",
        self.CYW43_LINK_NONET: "No matching SSID found (could be out of range, or down)",
        self.CYW43_LINK_BADAUTH: "Authentication failure",
        }
        self.ip = "Unknown"
        self.subnet = "Unknown"
        self.gateway = "Unknown"
        self.dns = "Unknown"
        self.ntp_last_synced_timestamp = 0

        self.configure_wifi()
        self.configure_error_handling()
        self.log.info("> Wireless Network initialized")

    def configure_wifi(self) -> None:
        self.log.info("> Configuring WiFi...")
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.config(pm=self.disable_power_management)
        self.mac = hexlify(self.wlan.config('mac'),':').decode()
        self.mac_no_colons = self.mac.replace(":", "")
        self.log.info(f"> MAC address: {self.mac}")
        
        if config.CUSTOM_HOSTNAME:
            self.hostname = config.CUSTOM_HOSTNAME
        else:
            self.hostname = "smibhid-" + self.mac_no_colons[-6:]
        self.log.info(f"> Hostname: {self.hostname}")
        network.hostname(self.hostname)
        
        # Log WiFi configuration
        self.log.info(f"> WiFi SSID: {self.wifi_ssid}")
        self.log.info(f"> WiFi Country: {self.wifi_country}")

    def startup(self) -> None:
        #self.log.info("Starting wifi network monitor")
        #create_task(self.network_monitor())
        create_task(self.check_network_access())

    def configure_error_handling(self) -> None:
        self.error_handler = ErrorHandler("Wifi")
        self.errors = {
            "CON": "Wifi connect"
        }

        for error_key, error_message in self.errors.items():
            self.error_handler.register_error(error_key, error_message)

    def dump_status(self):
        status = self.wlan.status()
        self.log.info(f"WiFi status: {status} ({self.status_names[status]})")
        return status
    
    async def wait_status(self, expected_status, *, timeout=config.WIFI_CONNECT_TIMEOUT_SECONDS, tick_sleep=0.5) -> bool:
        for unused in range(ceil(timeout / tick_sleep)):
            await sleep(tick_sleep)
            status = self.dump_status()
            if status == expected_status:
                return True
            if status < 0:
                raise Exception(self.status_names[status])
        return False
    
    async def disconnect_wifi_if_necessary(self) -> None:
        status = self.dump_status()
        if status >= self.CYW43_LINK_JOIN and status <= self.CYW43_LINK_UP:
            self.log.info("> Disconnecting existing WiFi connection...")
            self.wlan.disconnect()
            try:
                await self.wait_status(self.CYW43_LINK_DOWN)
            except Exception as x:
                raise Exception(f"Failed to disconnect: {x}")
        self.log.info("> Ready for new connection")
    
    def generate_connection_info(self, elapsed_ms) -> None:
        self.ip, self.subnet, self.gateway, self.dns = self.wlan.ifconfig()
        self.log.info(f"> IP: {self.ip}, Subnet: {self.subnet}, Gateway: {self.gateway}, DNS: {self.dns}")
        
        self.log.info(f"> Connection time: {elapsed_ms}ms")
        if elapsed_ms > 5000:
            self.log.warn(f"! WiFi connection took {elapsed_ms}ms (slow connection)")

    async def connection_error(self) -> None:
        self.log.error("! WiFi connection error")
        if not self.error_handler.is_error_enabled("CON"):
            self.error_handler.enable_error("CON")
        await self.status_led.async_flash(2, 2)

    async def connection_success(self) -> None:
        self.log.info("> WiFi connection successful")
        if self.error_handler.is_error_enabled("CON"):
            self.error_handler.disable_error("CON")
        await self.status_led.async_flash(1, 2)

    async def attempt_ap_connect(self) -> None:
        self.log.info(f"> Connecting to SSID '{self.wifi_ssid}'...")
        await self.disconnect_wifi_if_necessary()
        self.wlan.connect(self.wifi_ssid, self.wifi_password)
        try:
            await self.wait_status(self.CYW43_LINK_UP)
        except Exception as x:
            await self.connection_error()
            raise Exception(f"Failed to connect to SSID '{self.wifi_ssid}': {x}")
        await self.connection_success()
        self.log.info("> Connected successfully!")
    
    async def connect_wifi(self) -> None:
        self.log.info("> Starting WiFi connection process...")
        start_ms = ticks_ms()
        try:
            await self.attempt_ap_connect()
        except Exception:
            raise Exception("Failed to connect to network")

        elapsed_ms = ticks_ms() - start_ms
        self.generate_connection_info(elapsed_ms)

    def get_status(self) -> int:
        return self.wlan.status()
    
    async def network_retry_backoff(self) -> None:
        self.log.info(f"> WiFi retry backoff: waiting {config.WIFI_RETRY_BACKOFF_SECONDS} seconds...")
        await self.status_led.async_flash((config.WIFI_RETRY_BACKOFF_SECONDS * self.led_retry_backoff_frequency), self.led_retry_backoff_frequency)

    async def check_network_access(self) -> bool:
        self.log.info("> Checking for network access...")
        retries = 0
        max_retries = config.WIFI_CONNECT_RETRIES
        
        # Check if already connected
        if self.get_status() == 3:  # Already connected with IP
            self.log.info("> WiFi already connected")
            return True
        
        while retries <= max_retries:
            self.log.info(f"> Connecting to WiFi network '{self.wifi_ssid}' (attempt {retries + 1} of {max_retries + 1})...")
            
            try:
                await self.connect_wifi()
                self.log.info("> Connected to wireless network!")
                
                # Sync RTC from NTP if needed
                if self.ntp_last_synced_timestamp == 0 or (time() - self.ntp_last_synced_timestamp) > config.NTP_SYNC_INTERVAL_SECONDS:
                    self.log.info(f"> Syncing RTC from NTP (not synced in {config.NTP_SYNC_INTERVAL_SECONDS} seconds)...")
                    await self.async_sync_rtc_from_ntp()
                
                return True
                
            except Exception as e:
                self.log.warn(f"! WiFi connection failed: {e}")
                retries += 1
                
                if retries <= max_retries:
                    self.log.info(f"> Retrying WiFi connection in {config.WIFI_RETRY_BACKOFF_SECONDS} seconds...")
                    await self.network_retry_backoff()
                else:
                    self.log.error("! Unable to connect to wireless network after {max_retries + 1} attempts")
                    return False
        
        self.log.error("! Unable to connect to wireless network")
        return False

    async def network_monitor(self) -> None:
        while True:
            await self.check_network_access()
            await sleep(5)
    
    def get_mac(self) -> str:
        return self.mac
    
    def get_wlan_status_description(self, status) -> str:
        description = self.status_names[status]
        return description
    
    def get_all_data(self) -> dict:
        all_data = {}
        all_data['mac'] = self.get_mac()
        status = self.get_status()
        all_data['status description'] = self.get_wlan_status_description(status)
        all_data['status code'] = status
        return all_data

    def get_hostname(self) -> str:
        return self.hostname
    
    async def async_get_timestamp_from_ntp(self) -> tuple:
        ntp_host = "pool.ntp.org"
        port = 123
        buf_size = 48
        ntp_request_id = 0x1b
        timestamp = (2000, 1, 1, 0, 0, 0, 0, 0)

        try:
            query = bytearray(buf_size)
            query[0] = ntp_request_id
            address = getaddrinfo(ntp_host, port)[0][-1]
            udp_socket = socket(AF_INET, SOCK_DGRAM)
            udp_socket.setblocking(False)
            
            socket.sendto(udp_socket, query, address)
   
            timeout_ms = 5000
            start_time = ticks_ms()
            while (ticks_ms() - start_time) < timeout_ms:
                try:
                    data, _ = udp_socket.recvfrom(buf_size)
                    udp_socket.close()
                    
                    local_epoch = 2208988800
                    timestamp = struct.unpack("!I", data[40:44])[0] - local_epoch
                    timestamp = gmtime(timestamp)
                    break
                except OSError:
                    await sleep(0.1)

        except Exception as e:
            self.log.error(f"Failed to get NTP time: {e}")

        return timestamp

    async def async_sync_rtc_from_ntp(self) -> tuple:
        try:
            self.log.info("> Fetching time from NTP server...")
            timestamp = await self.async_get_timestamp_from_ntp()
            pre_sync = time()
            RTC().datetime((
                timestamp[0], timestamp[1], timestamp[2], timestamp[6],
                timestamp[3], timestamp[4], timestamp[5], 0))
            self.ntp_last_synced_timestamp = time()
            drift = pre_sync - time()
            self.log.info(f"> RTC synced from NTP successfully, drift: {drift} seconds")
        except Exception as e:
            self.log.error(f"! Failed to sync RTC from NTP: {e}")
        return timestamp