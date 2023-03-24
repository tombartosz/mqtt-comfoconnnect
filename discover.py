import mqtt_utils
from const import *
from sensor_utils import *


def discover_numeric():
    for sensor in SENSORS.values():
        if sensor.id in NUMERIC_SENSORS:
            print("Discover: " + str(sensor.name))
            discover_topic = "homeassistant/sensor/comfoconnect/" + urlify(sensor.name) + "/config"
            device = ", \"device\":{\"ids\":\"comfoconnect\",\"mf\":\"comfoconnect\",\"name\":\"comfoconnect\",\"sw\":\"1\"}"

            unit = ""
            if sensor.unit is not None:
                unit = ", \"unit_of_meas\": \"" + sensor.unit + "\""
            state_topic = topic + "sensor/" + urlify(sensor.name)
            payload = "{ \"name\": \"" + str(sensor.name) \
                      + "\", \"qos\":0, \"stat_t\": \"" + state_topic \
                      + "\", \"uniq_id\": \"" + urlify(sensor.name) + "\"" \
                      + "" + unit + device \
                      + ", \"avty\":{\"topic\":\"comfoconnect/status\", \"payload_available\":\"Online\", \"payload_not_available\":\"Offline\" } , \"state_class\":\"measurement\"}"
            mqtt_utils.client.publish(discover_topic, payload, retain=True)
