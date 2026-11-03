import requests
import pytest

from jcan.vin_decoder import VinDecodeError, decode_vin


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


def test_decode_vin_success():
    def fake_get(url, timeout):
        return FakeResponse({"Results": [{"Make": "Honda", "Model": "Civic", "ModelYear": "2018"}]})

    result = decode_vin("1HGCM82633A004352", http_get=fake_get)
    assert result == {"make": "Honda", "model": "Civic", "year": "2018"}


def test_decode_vin_not_found_raises():
    def fake_get(url, timeout):
        return FakeResponse({"Results": [{"Make": "", "Model": "", "ModelYear": ""}]})

    with pytest.raises(VinDecodeError):
        decode_vin("00000000000000000", http_get=fake_get)


def test_decode_vin_network_error_raises():
    def fake_get(url, timeout):
        raise requests.ConnectionError("no network")

    with pytest.raises(VinDecodeError):
        decode_vin("1HGCM82633A004352", http_get=fake_get)


def test_decode_vin_http_error_raises():
    def fake_get(url, timeout):
        return FakeResponse({}, status_code=500)

    with pytest.raises(VinDecodeError):
        decode_vin("1HGCM82633A004352", http_get=fake_get)
