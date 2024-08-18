from config import INFLUXDB_BUCKET, INFLUXDB_TOKEN, INFLUXDB_URL, INFLUXDB_ORG, INFLUXDB_DEVICE
from lib.destinations.destination import Destination

class InfluxDB(Destination):
    def __init__(self) -> None:
        super().__init__("InfluxDB")

    def url_encode(self, url: str) -> str:
        result = ""
        for c in url:
            if c.isalpha() or c.isdigit() or c in ["-", "_", "."]:
                result += c
            elif c == " ":
                result += "+"
            else:
                result += f"%{ord(c):02X}"
        return result

    async def async_upload_data(self, data: dict) -> int:
        """
        Upload readings to influxDB.
        Expected format of readings: {
            "timestamp": "2021-01-01T00:00:00Z", 
            "readings": {
                "temperature": 20.0, 
                "humidity": 50.0, ...
                }
            }
        """
        bucket = INFLUXDB_BUCKET
        self.log.info(f"Uploading readings to InfluxDB: {data} - Bucket: {INFLUXDB_BUCKET}")
        readings = ""

        for key, value in data["readings"].items():
            if readings != "":
                readings += "\n"
            timestamp = data["timestamp"]

            device = INFLUXDB_DEVICE
            readings += f"{key},device={device} value={value} {timestamp}"

        influxdb_token = INFLUXDB_TOKEN
        headers = {
        "Authorization": f"Token {influxdb_token}",
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Length": str(len(readings))
        }

        url = INFLUXDB_URL
        org = INFLUXDB_ORG
        url += f"/api/v2/write?precision=s&org={self.url_encode(org)}&bucket={self.url_encode(bucket)}"
        self.log.info(f"URL: {url}")
        self.log.info(f"headers: {headers}")
        self.log.info(f"data: {readings}")

        try:
            return_data = await self.http.async_make_request("POST", headers, url, readings)
            self.log.info(f"Return data: {return_data}")
            return self.UPLOAD_SUCCESS
        except Exception as e:
            self.log.error(f"Failed to upload data to InfluxDB: {e}")
            return self.UPLOAD_FAILED