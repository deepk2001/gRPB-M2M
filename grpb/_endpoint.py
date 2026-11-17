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


INCOMING_ALIASES = 64   # topic aliases we accept from the broker per connection


def publish_packet_size(topic: str, payload_len: int, props_len: int = 1, qos: int = 1) -> int:
    """Bytes of an MQTT 5 PUBLISH packet: fixed header, remaining-length varint, topic, packet id
    (QoS > 0), properties (props_len includes its own length byte) and payload."""
    remaining = 2 + len(topic.encode()) + (2 if qos else 0) + props_len + payload_len
    varint = 1 if remaining < 128 else 2 if remaining < 16384 else 3 if remaining < 2097152 else 4
    return 1 + varint + remaining


def _props_len(props: Properties | None) -> int:
    return len(props.pack()) if props is not None else 1


class Endpoint:
    """Wraps a paho client. `ready` is set while connected *and* subscribed; `settled` is set
    once the first connection attempt has finished either way (used for fail-fast calls)."""

    def __init__(self, client_id: str, host: str, port: int, *,
                 subscriptions: list[str],
                 on_message: Callable[[str, bytes], None],
                 will: tuple[str, bytes, bool] | None = None,
                 on_ready: Callable[[], None] | None = None,
                 on_lost: Callable[[], None] | None = None,
                 keepalive: int = 15,
                 topic_aliases: bool = True) -> None:
        self.client_id, self.host, self.port, self.keepalive = client_id, host, port, keepalive
        self.ready = threading.Event()
        self.settled = threading.Event()
        self._subscriptions = subscriptions
        self._on_message_cb, self._on_ready_cb, self._on_lost_cb = on_message, on_ready, on_lost
        self._sub_mid: int | None = None
        self._closing = False
        self._stats_lock = threading.Lock()
        self._stats = {"msgs_out": 0, "bytes_out": 0, "msgs_in": 0, "bytes_in": 0}
        # MQTT 5 topic aliases: after the first message on a topic, send a 2-byte alias instead of
        # the topic string. Aliases live only as long as one connection.
        self._use_aliases = topic_aliases
        self._aliases: dict[str, int] = {}
        self._alias_max = 0
        self._pub_lock = threading.Lock()
        self._in_aliases: dict[int, str] = {}   # aliases the broker uses towards us (network thread only)

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
        props = None
        if self._use_aliases:
            props = Properties(PacketTypes.CONNECT)
            props.TopicAliasMaximum = INCOMING_ALIASES   # let the broker shorten what it sends us too
        self._client.connect_async(self.host, self.port, keepalive=self.keepalive, properties=props)
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
        # One lock around alias choice and the send, so a topic's first (full) message always goes
        # out before the alias-only ones.
        with self._pub_lock:
            send_topic = topic
            if self._use_aliases and self.ready.is_set():
                alias = self._aliases.get(topic)
                if alias is None and len(self._aliases) < self._alias_max:
                    alias = self._aliases[topic] = len(self._aliases) + 1   # first use: topic + alias
                elif alias is not None:
                    send_topic = ""                                          # later: alias only
                if alias is not None:
                    props = props or Properties(PacketTypes.PUBLISH)
                    props.TopicAlias = alias
            self._count("out", publish_packet_size(send_topic, len(payload), _props_len(props)))
            return self._client.publish(send_topic, payload, qos=1, retain=retain, properties=props)

    def _reset_aliases(self, alias_max: int) -> None:
        """New connection: forget aliases, and give any queued (to be resent) message its topic back."""
        with self._pub_lock:
            topic_of = {a: t for t, a in self._aliases.items()}
            self._aliases.clear()
            self._alias_max = alias_max if self._use_aliases else 0
            with self._client._out_message_mutex:
                for m in self._client._out_messages.values():
                    alias = getattr(m.properties, "TopicAlias", None) if m.properties else None
                    if alias is not None:
                        if not m._topic:
                            m._topic = topic_of.get(alias, "").encode()
                        delattr(m.properties, "TopicAlias")

    def stats(self) -> dict[str, int]:
        """MQTT PUBLISH packets and bytes sent and received on this connection so far (exact packet
        sizes, including topics and properties; PUBACKs and keepalives are not counted)."""
        with self._stats_lock:
            return dict(self._stats)

    def _count(self, direction: str, size: int) -> None:
        with self._stats_lock:
            self._stats["msgs_" + direction] += 1
            self._stats["bytes_" + direction] += size

    # --- paho callbacks (network thread) -------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("%s: broker %s:%s refused connection: %s", self.client_id, self.host, self.port, reason_code)
            self.settled.set()
            return
        self._reset_aliases(getattr(properties, "TopicAliasMaximum", 0) if properties else 0)
        self._in_aliases.clear()
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
        props = getattr(msg, "properties", None)
        topic = msg.topic
        self._count("in", publish_packet_size(topic, len(msg.payload), _props_len(props), msg.qos))
        alias = getattr(props, "TopicAlias", None) if props is not None else None
        if alias is not None:   # paho hands aliased messages over with an empty topic: resolve it
            if topic:
                self._in_aliases[alias] = topic
            else:
                topic = self._in_aliases.get(alias, "")
                if not topic:
                    log.warning("%s: message with unknown topic alias %d dropped", self.client_id, alias)
                    return
        try:
            self._on_message_cb(topic, msg.payload)
        except Exception:  # never let one bad message kill the network thread
            log.exception("%s: error handling message on %s", self.client_id, msg.topic)
