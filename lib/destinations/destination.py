from lib.ulogging import uLogger
from lib.async_request import AsyncRequest

class Destination():
    """
    Base destination class for uploading data.
    """
    def __init__(self, name: str) -> None:
        self.log = uLogger(name)
        self.name = name
        self.log.info(name)
        self.UPLOAD_SUCCESS = 0
        self.UPLOAD_FAILED = 1
        self.http = AsyncRequest()

    async def async_upload_data(self, data: dict) -> int:
        """
        Upload readings to destination.
        Expected format of readings: {
            "timestamp": "2021-01-01T00:00:00Z", 
            "readings": {
                "temperature": 20.0, 
                "humidity": 50.0, ...
                }
            }
        """
        self.log.info(f"Uploading readings to {self.name}: {data}")
        return self.UPLOAD_SUCCESS
