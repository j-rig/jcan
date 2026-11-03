import requests

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"


class VinDecodeError(Exception):
    pass


def decode_vin(vin: str, http_get=requests.get) -> dict:
    try:
        response = http_get(NHTSA_URL.format(vin=vin), timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise VinDecodeError(f"VIN decode request failed: {exc}") from exc

    data = response.json()
    results = data.get("Results") or []
    if not results:
        raise VinDecodeError("No decode results returned")

    result = results[0]
    make = result.get("Make") or ""
    model = result.get("Model") or ""
    year = result.get("ModelYear") or ""
    if not make:
        raise VinDecodeError("VIN could not be decoded (no make returned)")

    return {"make": make, "model": model, "year": year}
