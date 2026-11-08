import json
import socket

from jcan.udp_stream import UdpStreamer


def test_send_emits_jsonl_datagram():
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.bind(("127.0.0.1", 0))
    recv_sock.settimeout(2.0)
    host, port = recv_sock.getsockname()

    streamer = UdpStreamer(host, port)
    try:
        streamer.send("rpm", 1234.0, "rpm")
        data, _ = recv_sock.recvfrom(4096)
    finally:
        streamer.close()
        recv_sock.close()

    text = data.decode("utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == {"rpm": {"value": 1234.0, "unit": "rpm"}}


def test_send_accumulates_all_known_pids_into_one_dict():
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.bind(("127.0.0.1", 0))
    recv_sock.settimeout(2.0)
    host, port = recv_sock.getsockname()

    streamer = UdpStreamer(host, port)
    try:
        streamer.send("rpm", 1234.0, "rpm")
        recv_sock.recvfrom(4096)
        streamer.send("speed", 60.0, "km/h")
        data, _ = recv_sock.recvfrom(4096)
    finally:
        streamer.close()
        recv_sock.close()

    assert json.loads(data.decode("utf-8")) == {
        "rpm": {"value": 1234.0, "unit": "rpm"},
        "speed": {"value": 60.0, "unit": "km/h"},
    }


def test_send_ignores_failures(monkeypatch):
    streamer = UdpStreamer("127.0.0.1", 1)

    def raise_oserror(self, *args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(socket.socket, "sendto", raise_oserror)
    streamer.send("rpm", 1234.0, "rpm")  # must not raise
    streamer.close()
