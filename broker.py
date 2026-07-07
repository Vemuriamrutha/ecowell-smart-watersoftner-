"""
broker.py — Pure Python MQTT 3.1.1 Broker (Zero external dependencies)
EcoWell Smart Water Softener — Self-contained MQTT broker for demo.

This implements a minimal MQTT 3.1.1 broker using only Python standard library.
Supports: CONNECT, PUBLISH, SUBSCRIBE, PINGREQ/PINGRESP, DISCONNECT

Run: python broker.py
"""

import socket
import threading
import struct
import time
import sys

# ── MQTT Packet Types ─────────────────────────────────────────────────────────
CONNECT     = 1
CONNACK     = 2
PUBLISH     = 3
PUBACK      = 4
SUBSCRIBE   = 8
SUBACK      = 9
UNSUBSCRIBE = 10
UNSUBACK    = 11
PINGREQ     = 12
PINGRESP    = 13
DISCONNECT  = 14

HOST = "0.0.0.0"
PORT = 1883


def encode_remaining_length(length):
    result = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length > 0:
            byte |= 0x80
        result.append(byte)
        if length == 0:
            break
    return bytes(result)


def decode_remaining_length(data, start):
    multiplier = 1
    value = 0
    idx = start
    while True:
        byte = data[idx]
        value += (byte & 0x7F) * multiplier
        multiplier *= 128
        idx += 1
        if not (byte & 0x80):
            break
        if multiplier > 128 * 128 * 128:
            raise ValueError("Malformed remaining length")
    return value, idx


def read_string(data, pos):
    length = struct.unpack_from(">H", data, pos)[0]
    pos += 2
    return data[pos:pos + length].decode("utf-8", errors="replace"), pos + length


def make_connack(return_code=0):
    return bytes([CONNACK << 4, 2, 0, return_code])


def make_suback(packet_id, qos_list):
    payload = struct.pack(">H", packet_id) + bytes(qos_list)
    header  = bytes([SUBACK << 4]) + encode_remaining_length(len(payload))
    return header + payload


def make_pingresp():
    return bytes([PINGRESP << 4, 0])


def make_publish(topic, payload_bytes, qos=0, packet_id=None):
    topic_b = topic.encode("utf-8")
    body    = struct.pack(">H", len(topic_b)) + topic_b
    if qos > 0 and packet_id is not None:
        body += struct.pack(">H", packet_id)
    body += payload_bytes
    flags  = (PUBLISH << 4) | (qos << 1)
    header = bytes([flags]) + encode_remaining_length(len(body))
    return header + body


class MQTTBroker:

    def __init__(self, host=HOST, port=PORT):
        self.host        = host
        self.port        = port
        self.clients     = {}    # socket → {"id": str, "subs": set}
        self.subscribers = {}    # topic → set of sockets
        self.lock        = threading.Lock()

    # ── Topic matching ──────────────────────────────────────────────────

    def topic_matches(self, pattern, topic):
        """MQTT wildcard matching: # and +"""
        if pattern == "#":
            return True
        p_parts = pattern.split("/")
        t_parts = topic.split("/")
        for i, p in enumerate(p_parts):
            if p == "#":
                return True
            if i >= len(t_parts):
                return False
            if p != "+" and p != t_parts[i]:
                return False
        return len(p_parts) == len(t_parts)

    # ── Publish to all matching subscribers ─────────────────────────────

    def distribute(self, topic, payload_bytes, sender_sock=None):
        pub = make_publish(topic, payload_bytes)
        with self.lock:
            targets = list(self.subscribers.items())
        for pattern, socks in targets:
            if self.topic_matches(pattern, topic):
                with self.lock:
                    sock_list = list(socks)
                for sock in sock_list:
                    if sock is not sender_sock:  # don't echo back
                        try:
                            sock.sendall(pub)
                        except Exception:
                            pass

    # ── Handle one client connection ─────────────────────────────────────

    def handle_client(self, sock, addr):
        print(f"  [+] Client connected: {addr[0]}:{addr[1]}")
        buf = b""
        client_id = None
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk

                # Process all complete packets in buffer
                while len(buf) >= 2:
                    pkt_type = (buf[0] >> 4)
                    try:
                        remaining, hdr_end = decode_remaining_length(buf, 1)
                    except (ValueError, IndexError):
                        break

                    total = hdr_end + remaining
                    if len(buf) < total:
                        break  # wait for more data

                    packet = buf[:total]
                    buf    = buf[total:]

                    # ── CONNECT ──────────────────────────────────────
                    if pkt_type == CONNECT:
                        pos = hdr_end
                        _, pos = read_string(packet, pos)  # protocol name
                        pos += 1                           # protocol level
                        flags = packet[pos]; pos += 1
                        pos += 2                           # keep-alive
                        client_id, pos = read_string(packet, pos)

                        with self.lock:
                            self.clients[sock] = {"id": client_id, "subs": set()}
                        print(f"  [CONNECT] client_id={client_id}")
                        sock.sendall(make_connack(0))

                    # ── SUBSCRIBE ─────────────────────────────────────
                    elif pkt_type == SUBSCRIBE:
                        pos = hdr_end
                        pkt_id = struct.unpack_from(">H", packet, pos)[0]; pos += 2
                        qos_list = []
                        while pos < total:
                            topic_filter, pos = read_string(packet, pos)
                            qos = packet[pos]; pos += 1
                            qos_list.append(0)  # grant QoS 0
                            with self.lock:
                                self.subscribers.setdefault(topic_filter, set()).add(sock)
                                if sock in self.clients:
                                    self.clients[sock]["subs"].add(topic_filter)
                            print(f"  [SUBSCRIBE] {client_id} → {topic_filter}")
                        sock.sendall(make_suback(pkt_id, qos_list))

                    # ── PUBLISH ───────────────────────────────────────
                    elif pkt_type == PUBLISH:
                        pos  = hdr_end
                        flags = buf[0] if buf else 0  # already advanced; use original
                        qos  = (packet[0] >> 1) & 0x03
                        topic, pos = read_string(packet, pos)
                        if qos > 0:
                            pkt_id = struct.unpack_from(">H", packet, pos)[0]; pos += 2
                            sock.sendall(bytes([PUBACK << 4, 2]) + struct.pack(">H", pkt_id))
                        payload_bytes = packet[pos:]
                        print(f"  [PUBLISH]   {client_id} → {topic} ({len(payload_bytes)}B)")
                        self.distribute(topic, payload_bytes, sender_sock=sock)

                    # ── PINGREQ ───────────────────────────────────────
                    elif pkt_type == PINGREQ:
                        sock.sendall(make_pingresp())

                    # ── DISCONNECT ────────────────────────────────────
                    elif pkt_type == DISCONNECT:
                        return

        except (ConnectionResetError, OSError):
            pass
        finally:
            self._cleanup(sock, addr)

    def _cleanup(self, sock, addr):
        with self.lock:
            info = self.clients.pop(sock, {})
            for topic in info.get("subs", []):
                self.subscribers.get(topic, set()).discard(sock)
            # Remove empty topic sets
            empty = [t for t, s in self.subscribers.items() if not s]
            for t in empty:
                del self.subscribers[t]
        try:
            sock.close()
        except Exception:
            pass
        print(f"  [-] Client disconnected: {addr[0]}:{addr[1]}")

    # ── Start server ─────────────────────────────────────────────────────

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((self.host, self.port))
        except OSError as e:
            if "10048" in str(e) or "Address already in use" in str(e):
                print(f"[Broker] Port {self.port} already in use — another broker may be running.")
                print("[Broker] Continuing (assuming external broker is available)...")
                return
            raise
        server.listen(50)

        print("=" * 55)
        print("  EcoWell Pure-Python MQTT Broker")
        print(f"  Listening on {self.host}:{self.port}")
        print("  Press Ctrl+C to stop.")
        print("=" * 55)

        try:
            while True:
                sock, addr = server.accept()
                t = threading.Thread(
                    target=self.handle_client,
                    args=(sock, addr),
                    daemon=True,
                )
                t.start()
        except KeyboardInterrupt:
            print("\n[Broker] Shutting down.")
        finally:
            server.close()


if __name__ == "__main__":
    broker = MQTTBroker()
    broker.start()
