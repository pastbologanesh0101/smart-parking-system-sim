"""
Demo script: runs the SIMULATED sensor fleet against a locally running
Smart Parking System server, POSTing random occupancy events to the real
/api/sensors/occupancy endpoint over HTTP, the same way real hardware
sensors would (but there is no real hardware here -- see app/sensors.py
and README.md for the full explanation).

Usage (with the dev server already running via `python run.py`):

    python scripts/simulate_sensors.py --lot-id 1 --iterations 10

Requires the `requests` package (already in requirements.txt).
"""
import argparse
import sys

import requests

from app.sensors import run_simulation_loop


def get_spot_ids(base_url: str, lot_id: int | None):
    params = {"lot_id": lot_id} if lot_id is not None else {}
    resp = requests.get(f"{base_url}/api/spots", params=params, timeout=5)
    resp.raise_for_status()
    return [s["id"] for s in resp.json()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--lot-id", type=int, default=None)
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()

    try:
        spot_ids = get_spot_ids(args.base_url, args.lot_id)
    except requests.RequestException as exc:
        print(f"Could not reach {args.base_url}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not spot_ids:
        print("No spots found -- create a lot and spots first via the API.", file=sys.stderr)
        sys.exit(1)

    print(f"Simulating sensor events for {len(spot_ids)} spot(s)...")
    run_simulation_loop(base_url=args.base_url, spot_ids=spot_ids, iterations=args.iterations)
    print("Done.")


if __name__ == "__main__":
    main()
