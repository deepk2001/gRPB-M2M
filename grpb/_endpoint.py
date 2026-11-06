"""One MQTT v5 connection shared by a channel or a server: reconnects, resubscribes, Last Will."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.subscribeoptions import SubscribeOptions

log = logging.getLogger("grpb")


class Endpoint:
    """Wraps a paho client. `ready` is set while connected *and* subscribed; `settled` is set
    once the first connection attempt has finished either way (used for fail-fast calls)."""

    def __init__(self, client_id: str, host: str, port: int, *,
                 subscriptions: list[str],
                 on_message: Callable[[str, bytes], None],
                 will: tuple[str, bytes, bool] | None = None,
                 on_ready: Callable[[], None] | None = None,
                 on_lost: Callable[[], None] | None = None,
                 keepalive: int = 15) -> None:
        self.client_id, self.host, self.port, self.keepalive = client_id, host, port, keepalive
        self.ready = threading.Event()
        self.settled = threading.Event()
        self._subscriptions = subscriptions
        self._on_message_cb, self._on_ready_cb, self._on_lost_cb = on_message, on_ready, on_lost
        self._sub_mid: int | None = None
        self._closing = False

        c = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id, protocol=mqtt.MQTTv5)
        if will:
            c.will_set(will[0], will[1], qos=1, retain=will[2])
        c.reconnect_delay_set(min_delay=1, max_delay=10)
        c.on_connect = self._on_connect
        c.on_connect_fail = self._on_connect_fail
        c.on_disconnect = self._on_disconnect
        c.on_subscribe = self._on_subscribe
        c.on_message = self._on_message
        self._client = c

    def start(self) -> None:
        self._client.connect_async(self.host, self.port, keepalive=self.keepalive)
        self._client.loop_start()

    def close(self) -> None:
        self._closing = True
        self._client.disconnect()
        self._client.loop_stop()
        self.ready.clear()

    def publish(self, topic: str, payload: bytes, *, retain: bool = False,
                expiry_s: int | None = None) -> mqtt.MQTTMessageInfo:
        props = None
        if expiry_s:
            # The broker drops the message if it can't be delivered in time; no clock sync needed.
            props = Properties(PacketTypes.PUBLISH)
            props.MessageExpiryInterval = expiry_s
        return self._client.publish(topic, payload, qos=1, retain=retain, properties=props)

    # --- paho callbacks (network thread) -------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("%s: broker %s:%s refused connection: %s", self.client_id, self.host, self.port, reason_code)
            self.settled.set()
            return
        result, self._sub_mid = client.subscribe([(t, SubscribeOptions(qos=1)) for t in self._subscriptions])

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties) -> None:
        if mid != self._sub_mid:
            return
        log.debug("%s: connected to %s:%s", self.client_id, self.host, self.port)
        self.ready.set()
        self.settled.set()
        if self._on_ready_cb:
            self._on_ready_cb()

    def _on_connect_fail(self, client, userdata) -> None:
        log.debug("%s: cannot reach broker %s:%s", self.client_id, self.host, self.port)
        self.settled.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        was_ready = self.ready.is_set()
        self.ready.clear()
        self.settled.set()
        if was_ready and not self._closing:
            log.info("%s: lost broker connection (%s); reconnecting", self.client_id, reason_code)
            if self._on_lost_cb:
                self._on_lost_cb()

    def _on_message(self, client, userdata, msg) -> None:
        try:
            self._on_message_cb(msg.topic, msg.payload)
        except Exception:  # never let one bad message kill the network thread
            log.exception("%s: error handling message on %s", self.client_id, msg.topic)
