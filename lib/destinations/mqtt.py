from lib.ulogging import uLogger
from lib.mqttsimple import MQTTClient
from config import (
    MQTT_BROKER_ADDRESS,
    MQTT_BROKER_USERNAME,
    MQTT_BROKER_PASSWORD,
    MQTT_BROKER_CA_FILE,
    MQTT_TOPIC_PREFIX,
    CUSTOM_HOSTNAME
)
import json
from lib.destinations.destination import Destination


class MQTT(Destination):
    """
    MQTT destination for uploading weather data to an MQTT broker.
    """
    
    def __init__(self) -> None:
        super().__init__("MQTT")
        self.broker_address = MQTT_BROKER_ADDRESS
        self.username = MQTT_BROKER_USERNAME
        self.password = MQTT_BROKER_PASSWORD
        self.ca_file = MQTT_BROKER_CA_FILE
        self.topic_prefix = MQTT_TOPIC_PREFIX
        self.hostname = CUSTOM_HOSTNAME
        
    async def async_upload_data(self, data: dict) -> int:
        """
        Upload readings to MQTT broker.
        Expected format of readings: {
            "timestamp": "2021-01-01T00:00:00Z", 
            "readings": {
                "temperature": 20.0, 
                "humidity": 50.0, ...
                }
            }
        """
        if not self.broker_address:
            self.log.error("MQTT broker address not configured - skipping upload")
            return self.UPLOAD_FAILED
        
        try:
            # Prepare the MQTT topic and payload
            topic = self._get_topic()
            payload = self._prepare_payload(data)
            
            self.log.info(f"Publishing to MQTT topic: {topic}")
            self.log.info(f"MQTT payload: {payload}")
            
            # Create MQTT client and publish
            client_id = f"pico-weather-{self.hostname}"
            
            # Configure SSL if CA file is provided
            ssl_params = {}
            if self.ca_file:
                try:
                    with open(self.ca_file, "r") as f:
                        ssl_data = f.read()
                    ssl_params = {'cert': ssl_data}
                    use_ssl = True
                except Exception as e:
                    self.log.error(f"Failed to read CA file: {e}")
                    use_ssl = False
            else:
                use_ssl = False
            
            # Create and connect MQTT client
            mqtt_client = MQTTClient(
                client_id=client_id,
                server=self.broker_address,
                user=self.username,
                password=self.password,
                keepalive=60,
                ssl=use_ssl,
                ssl_params=ssl_params
            )
            
            mqtt_client.connect()
            
            # Publish the data
            mqtt_client.publish(topic, payload, retain=False, qos=0)
            
            # Disconnect
            mqtt_client.disconnect()
            
            self.log.info("Successfully published data to MQTT broker")
            return self.UPLOAD_SUCCESS
            
        except Exception as e:
            self.log.error(f"Failed to publish data to MQTT broker: {e}")
            # Try to disconnect if client exists
            try:
                if 'mqtt_client' in locals():
                    mqtt_client.disconnect()
            except:
                pass
            return self.UPLOAD_FAILED
    
    def _get_topic(self) -> str:
        """
        Generate the MQTT topic based on configuration.
        """
        if self.topic_prefix:
            return f"{self.topic_prefix}/{self.hostname}"
        else:
            return f"pico-weather/{self.hostname}"
    
    def _prepare_payload(self, data: dict) -> str:
        """
        Prepare the MQTT payload from the weather data.
        Convert the data to a suitable JSON format for MQTT.
        """
        # Extract readings and add timestamp
        payload_data = {
            "timestamp": data.get("timestamp", ""),
            "device": self.hostname,
            "readings": data.get("readings", {})
        }
        
        # Convert to JSON string
        return json.dumps(payload_data)