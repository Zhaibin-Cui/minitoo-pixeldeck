"""Finite offline driver simulation: ACKs, resend, heartbeats, timeout and raw RX.

This injects a tiny in-memory socket into the real driver. No Bluetooth socket,
media player, device configuration file or hardware connection is opened.
"""
import json
import queue
import threading

from PIL import Image

from pixeldeck import DeviceConfig, MiniToo
from pixeldeck.experimental.input_probe import PacketTap
from pixeldeck.protocol import DONE, READY, packet, valid


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class SimulatedSocket:
    def __init__(self, *, ready=True, done=True, resend=False):
        self.incoming = queue.Queue(maxsize=128)
        self.ready, self.done, self.resend = ready, done, resend
        self.closed = False
        self.sent_packets = self.sent_chunks = 0
        self.expected = 0
        self.received = set()
        self.requested = self.completed = False
        self.lock = threading.Lock()

    def settimeout(self, timeout):
        pass

    def connect(self, address):
        # Deliberately does not resolve or connect to the supplied synthetic address.
        pass

    def receive_later(self, data):
        self.incoming.put(bytes(data), timeout=1)

    def sendall(self, raw):
        check(not self.closed and valid(raw), 'Invalid simulated outbound packet')
        self.sent_packets += 1
        if raw[3] == 0x32:
            self.receive_later(packet(4, bytes((0x32, 0x55, raw[4]))))
            return
        check(raw[3] == 0x8B, 'The lab permits display and brightness only')
        if raw[4] == 0:
            self.expected = (int.from_bytes(raw[5:9], 'little')+255)//256
            self.received.clear()
            self.requested = self.completed = False
            if self.ready:
                self.receive_later(READY[:4])
                self.receive_later(READY[4:])
            return
        self.sent_chunks += 1
        index = int.from_bytes(raw[9:11], 'little')
        check(0 <= index < self.expected, 'Invalid simulated chunk number')
        self.received.add(index)
        if self.completed or len(self.received) != self.expected:
            return
        if self.resend and not self.requested:
            self.requested = True
            self.receive_later(packet(4, b'\x8b\x55\x01\x00\x00'))
        elif self.done:
            self.completed = True
            self.receive_later(DONE)

    def recv(self, maximum):
        return self.incoming.get()

    def shutdown(self, how):
        self.close()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.incoming.put_nowait(b'')
            except queue.Full:
                self.incoming.get_nowait()
                self.incoming.put_nowait(b'')


def configuration():
    # A required syntactically valid placeholder, used only by the injected socket.
    return DeviceConfig(address=':'.join(('00',)*6), chunk_delay_ms=0, timeout=0.1, retries=0)


def normal_transactions():
    simulated = SimulatedSocket(resend=True)
    tap = PacketTap(capacity=8)
    disconnected = threading.Event()
    image = Image.new('RGB', (160, 128), '#102838')
    with MiniToo(configuration(), socket_factory=lambda: simulated, packet_tap=tap,
                 on_disconnect=lambda error: disconnected.set()) as device:
        report = device.show(image)
        check(report['retransmissions'] == 1, 'Requested chunk was not retransmitted')
        check(device.brightness(50) == 50, 'Matching brightness ACK was not returned')
        for _ in range(1000):
            simulated.receive_later(packet(4, b'\xf7\x55\x00'))
        # This second completed transaction proves queued heartbeats were drained.
        device.show(image)
        check(len(device.trace) == 32, 'Trace did not retain its fixed bound')
        observations = tap.snapshot()
        check(observations['pending'] <= 8, 'Packet tap exceeded capacity')
        simulated.close()
        check(disconnected.wait(2), 'Disconnect callback did not arrive')
        check(not device.healthy, 'Disconnected device still reports healthy')
    return {'fragmented_ready': True, 'matching_completion': True,
            'chunk_retransmissions': report['retransmissions'], 'brightness_ack': 50,
            'idle_heartbeats_injected': 1000, 'trace_entries': 32,
            'tap_capacity': 8, 'tap_dropped': observations['dropped'],
            'disconnect_callback': True}


def missing_ack(ready):
    simulated = SimulatedSocket(ready=ready, done=False)
    with MiniToo(configuration(), socket_factory=lambda: simulated) as device:
        try:
            device.show(Image.new('RGB', (160, 128)))
        except TimeoutError:
            pass
        else:
            raise AssertionError('Missing ACK did not time out')
        check(ready or simulated.sent_chunks == 0, 'Payload was sent without READY')
    return {'missing': 'completion' if ready else 'ready', 'timed_out': True,
            'payload_chunks_sent': simulated.sent_chunks}


def raw_receive():
    simulated = SimulatedSocket()
    tap = PacketTap(capacity=8)
    with MiniToo(configuration(), socket_factory=lambda: simulated, packet_tap=tap,
                 channel=10, decode_packets=False) as device:
        simulated.receive_later(b'simulated-unframed-data')
        event = tap.get(timeout=2)
        check(event is not None and event.kind == 'rx_bytes', 'Raw bytes were not observed')
        try:
            device.show(Image.new('RGB', (160, 128)))
        except RuntimeError:
            pass
        else:
            raise AssertionError('Receive-only link allowed a transaction')
        check(simulated.sent_packets == 0, 'Receive-only link transmitted data')
    return {'raw_bytes_observed': len(event.data), 'transactions_rejected': True,
            'bytes_are_not_key_events': True}


def main():
    result = {'simulation': True, 'hardware_accessed': False,
              'transactions': normal_transactions(),
              'timeouts': [missing_ack(False), missing_ack(True)], 'raw_receive': raw_receive()}
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
