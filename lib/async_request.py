import lib.uaiohttpclient as httpclient
from json import loads
import gc
from lib.ulogging import uLogger

class AsyncRequest:
    def __init__(self) -> None:
        self.log = uLogger("RestAPI")
        
    async def async_make_request(self, method: str, headers: dict, url: str, data: str = "") -> dict:
        """
        Internal method for making an async request, provide the method, headers, full URL and body data.
        Returns the response data as a dict, throws an exception if the return status code is not 200 or 204.
        """
        gc.collect()

        self.log.info(f"Calling URL: {url}, with method: {method}")

        try:
            request = await httpclient.request(method, url, headers=headers, data=data)
            self.log.info(f"Request: {request}")
            response = await request.read()
            self.log.info(f"Response data: {response}")
            data = {}
            if response:
                data = loads(response)
                self.log.info(f"Data: {data}")
            
            if request.status == 200 or request.status == 204:
                self.log.info("Request processed sucessfully by server")
                return data
            else:
                raise ValueError(f"HTTP status code was not 200 or 204. Status code: {request.status}, HTTP response: {response}")
        except Exception as e:
            self.log.error(f"Failed to make HTTP request successfully: {url}. Exception: {e}")
            raise
        finally:
            gc.collect()