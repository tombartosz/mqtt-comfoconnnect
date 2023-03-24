""" aiocomfoconnect CLI application """
from __future__ import annotations

import asyncio
import threading

from aiocomfoconnect.bridge import Message
from paho.mqtt import client as mqtt_client

from aiocomfoconnect import DEFAULT_UUID
from aiocomfoconnect.comfoconnect import ComfoConnect
from aiocomfoconnect.discovery import discover_bridges
from aiocomfoconnect.exceptions import (
    ComfoConnectOtherSession,
)

import mqtt_utils
from discover import *
from mqtt_utils import *


def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
            client.publish(topic + "status", payload="Online", qos=0, retain=True)
            discover_numeric()

        else:
            print("Failed to connect, return code %d\n", rc)

    mqtt_utils.client = mqtt_client.Client(client_id)
    # client.username_pw_set(username, password)
    print("Connecting to MQTT")
    mqtt_utils.client.on_connect = on_connect
    mqtt_utils.client.will_set(topic + "status", payload="Offline", qos=0, retain=True)

    mqtt_utils.client.connect(broker, port)


next_speed: str = None
next_bypass: str = None
next_bypass_time: int = None


async def main():
    connect_mqtt()
    threading.Timer(33.0, important_sensors_timer).start()
    threading.Timer(5.0, all_sensors_timer).start()

    mqtt_utils.client.subscribe(topic + "cmd/bypass")
    mqtt_utils.client.on_message = on_message
    mqtt_utils.client.subscribe(topic + "cmd/speed")
    mqtt_utils.client.subscribe(topic + "cmd/speed_bin")
    mqtt_utils.client.loop_forever()


def on_message(client, userdata, msg):
    print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
    global next_speed
    global next_bypass
    global next_bypass_time
    if msg.topic == topic + "cmd/speed":
        next_speed = msg.payload.decode()
    if msg.topic == topic + "cmd/bypass":
        value: str = msg.payload.decode()
        if value.isnumeric():
            next_bypass_time = int(value)
            next_bypass = "on"
        else:
            next_bypass = msg.payload.decode()
    if msg.topic == topic + "cmd/speed_bin":
        value: str = msg.payload.decode()
        if value == "on":
            next_speed = "low"
        else:
            next_speed = "away"

    threading.Timer(0.1, important_sensors_timer_single).start()


def send_mqtt(topic_postfix: str, value: str):
    if mqtt_utils.client is not None:
        mqtt_utils.client.publish(topic + topic_postfix, value)


def important_sensors_timer():
    threading.Timer(33.0, important_sensors_timer).start()
    asyncio.run(important_sensors(), debug=True)


def important_sensors_timer_single():
    asyncio.run(important_sensors(), debug=True)


async def important_sensors():
    print("--- IMPORTANT SENSORS --")
    await run_show_sensors(IMPORTANT_SENSORS)


def all_sensors_timer():
    threading.Timer(300.0, all_sensors_timer).start()
    asyncio.run(all_sensors(), debug=True)


async def all_sensors():
    print("--- ALL SENSORS --")
    await run_show_sensors(ALL_SENSORS, True)


async def run_show_sensors(sensor_ids, show_alarm=False):
    try:
        uuid = DEFAULT_UUID
        """Connect to a bridge."""
        # Discover bridge so we know the UUID
        bridges = await discover_bridges(None)
        if not bridges:
            raise Exception("No bridge found")

        values = dict()

        def alarm_callback(node_id, errors):
            if show_alarm:
                """Print alarm updates."""
                print(f"Alarm received for Node {node_id}:")
                error_msg = ""
                for error_id, error in errors.items():
                    print(f"* {error_id}: {error}")
                    error_msg = error_msg + "[" + str(error_id) + "]" + str(error) + "; "
                send_mqtt("errors", error_msg)

        def sensor_callback(sensor, value):
            """Print sensor updates."""
            values[sensor.id] = value
            send_mqtt("sensor/" + urlify(sensor.name), value)
            print(f"{sensor.name:>40}: {value} {sensor.unit or ''}")
            if sensor.id == SENSOR_FAN_SPEED_MODE:
                if value == 0:
                    send_mqtt("sensor/" + urlify(sensor.name) + "_bin", "off")
                    send_mqtt("sensor/" + urlify(sensor.name) + "_enum", "away")
                else:
                    send_mqtt("sensor/" + urlify(sensor.name)+ "_bin", "on")
                    if value == 1:
                        send_mqtt("sensor/" + urlify(sensor.name) + "_enum", "low")
                    if value == 2:
                        send_mqtt("sensor/" + urlify(sensor.name) + "_enum", "medium")
                    if value == 3:
                        send_mqtt("sensor/" + urlify(sensor.name) + "_enum", "high")

        # Connect to the bridge
        comfoconnect = ComfoConnect(bridges[0].host, bridges[0].uuid, sensor_callback=sensor_callback,
                                    alarm_callback=alarm_callback)

        await comfoconnect.connect(uuid, False)
        msg: Message = await comfoconnect.cmd_start_session(False)
        print(type(msg))
        # convert into JSON:
        #  json_data = json.dumps(msg)
        global next_speed
        global next_bypass
        global next_bypass_time
        if next_speed is not None:
            await comfoconnect.set_speed(next_speed)
            next_speed = None
        if next_bypass is not None:
            timeout = -1
            if next_bypass_time is not None:
                timeout = next_bypass_time
                next_bypass_time = None
            await comfoconnect.set_bypass(next_bypass, timeout)
            next_bypass = None

        # Register all sensors
        for sensor in SENSORS.values():
            if sensor.id in sensor_ids:
                values[sensor.id] = None;
                await comfoconnect.register_sensor(sensor)

        cnt = 0
        while True:
            if None not in values.values():
                print("Disconnecting...")
                await comfoconnect.disconnect()
                return
            await asyncio.sleep(1)
            cnt = cnt + 1
            if cnt > 10:
                print("Disconnecting...")
                await comfoconnect.disconnect()
                return

        print("Disconnecting...")
        await comfoconnect.disconnect()
    except ComfoConnectOtherSession as other_session:
        msg: Message = other_session.args[0]
        message = "other device connected: " + str(msg.msg).strip()
        print("Connection refused: " + message)
        send_mqtt("exception", message)
    except ConnectionRefusedError as refused:
        message = refused.args[1]
        print("Connection refused: " + message)
        send_mqtt("exception", message)
    except Exception as ex:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(ex).__name__, ex.args)
        print(message)


if __name__ == "__main__":
    try:
        asyncio.run(main(), debug=True)
    except KeyboardInterrupt:
        pass
