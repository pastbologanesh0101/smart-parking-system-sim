# Smart Parking System (Simulated Sensors, Real Backend)

A small Flask + SQLite backend for a "smart" parking lot: real-time
availability, reservations with proper overlap checking, check-in/check-out
billing, and basic occupancy analytics.

## Honesty note: what's simulated and what's real

**There is no physical hardware anywhere in this project.** In a real smart
parking deployment, each spot would have an ultrasonic/inductive-loop sensor
that reports occupancy changes to a backend. Here, that sensor fleet is
**simulated in software** (`app/sensors.py`): it generates the same event
shape (`{"spot_id": ..., "occupied": true/false}`) that real hardware would
send, either on demand (used by the test suite, deterministic) or as a
background loop that POSTs events over HTTP at random intervals
(`scripts/simulate_sensors.py`, for a local demo).

Everything downstream of that event is **fully real**:

- the Flask backend and its `/api/sensors/occupancy` ingestion endpoint
- the SQLite database and SQLAlchemy models
- availability queries, spot-type filtering
- reservation overlap logic (interval math, not a stub)
- check-in / check-out and the billing calculation
- the analytics queries (peak occupancy hour, average duration per spot type)

If you swapped the simulator in `app/sensors.py` for a real HTTP client
talking to real hardware, nothing else in this repo would need to change.

## Data model

- **Lot**: `name`, `total_spots`
- **Spot**: `lot_id`, `spot_number`, `spot_type` (`standard` | `handicap` |
  `ev_charging`), `occupied`
- **Reservation**: `spot_id`, `license_plate`, `start_time`, `end_time`,
  `status` (`active` | `completed` | `cancelled`), plus `checked_in_at`,
  `checked_out_at`, `bill_amount` once check-in/check-out happen
- **RatePlan**: `spot_type`, `price_per_hour`

## Policy decisions (documented, and tested)

1. **Spot-type filtering is strict by default.** Searching availability for
   `spot_type=standard` will never return `handicap` or `ev_charging` spots.
   Pass `include_all_types=true` to see every type regardless of the
   `spot_type` filter.
2. **Handicap spots require explicit confirmation.** Reserving a `handicap`
   spot requires `accessibility_confirmed=true` in the request body,
   otherwise the reservation is rejected with `409`. This is a deliberate
   choice so accessibility spots can't be booked by default/accident by a
   generic search-and-reserve flow. `ev_charging` spots have no such
   restriction.
3. **Reservation overlap uses half-open interval math**: two windows
   `[start_a, end_a)` and `[start_b, end_b)` conflict iff
   `start_a < end_b and start_b < end_a`. A reservation that starts exactly
   when another ends on the same spot is **not** a conflict (back-to-back
   bookings are allowed). Only `active` reservations block new ones;
   `cancelled`/`completed` ones don't.
4. **Billing rule**: minimum charge is **1 hour**, even for a shorter stay.
   Beyond the first hour, the duration is rounded **up** to the nearest
   **15 minutes** (0.25h) — any partial 15-minute block is billed in full.
   Example: a 1h10m stay is billed as 1.25h. See
   `compute_billed_hours()` / `compute_bill()` in `app/services.py`.

## Running it

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python run.py            # dev server on http://127.0.0.1:5000
```

Run the tests:

```bash
pytest -v
```

Run the simulated sensor demo against a running server:

```bash
# terminal 1
python run.py

# terminal 2
python scripts/simulate_sensors.py --lot-id 1 --iterations 10
```

## Example usage

```bash
# Create a lot
curl -X POST http://127.0.0.1:5000/api/lots \
  -H "Content-Type: application/json" \
  -d '{"name": "Downtown Garage", "total_spots": 3}'
# -> {"id": 1, "name": "Downtown Garage", "total_spots": 3}

# Add spots
curl -X POST http://127.0.0.1:5000/api/lots/1/spots \
  -H "Content-Type: application/json" -d '{"spot_number": "A1", "spot_type": "standard"}'
curl -X POST http://127.0.0.1:5000/api/lots/1/spots \
  -H "Content-Type: application/json" -d '{"spot_number": "H1", "spot_type": "handicap"}'

# Set a rate plan
curl -X POST http://127.0.0.1:5000/api/rate-plans \
  -H "Content-Type: application/json" -d '{"spot_type": "standard", "price_per_hour": 4.0}'

# Check availability, standard spots only
curl "http://127.0.0.1:5000/api/availability?lot_id=1&spot_type=standard"

# Reserve a spot
curl -X POST http://127.0.0.1:5000/api/reservations \
  -H "Content-Type: application/json" \
  -d '{"spot_id": 1, "license_plate": "ABC-123", "start_time": "2026-01-01T10:00:00", "end_time": "2026-01-01T12:00:00"}'

# Check in / check out (drives billing)
curl -X POST http://127.0.0.1:5000/api/reservations/1/check-in -d '{"at": "2026-01-01T10:00:00"}' -H "Content-Type: application/json"
curl -X POST http://127.0.0.1:5000/api/reservations/1/check-out -d '{"at": "2026-01-01T12:10:00"}' -H "Content-Type: application/json"
# -> bill_amount computed from duration x rate, with the rounding rule above

# Analytics
curl "http://127.0.0.1:5000/api/analytics/peak-hour?lot_id=1"
curl "http://127.0.0.1:5000/api/analytics/average-duration?lot_id=1"
```

## API reference

| Method | Path | Description |
|---|---|---|
| GET | `/` | Service info |
| POST | `/api/lots` | Create a lot: `{name, total_spots}` |
| GET | `/api/lots` | List lots |
| POST | `/api/lots/<lot_id>/spots` | Add a spot: `{spot_number, spot_type}` |
| GET | `/api/spots?lot_id=` | List spots (optionally filter by lot) |
| GET | `/api/availability?lot_id=&spot_type=&include_all_types=` | Real-time free-spot count/list |
| POST | `/api/rate-plans` | Upsert a rate plan: `{spot_type, price_per_hour}` |
| GET | `/api/rate-plans` | List rate plans |
| POST | `/api/reservations` | Reserve a spot: `{spot_id, license_plate, start_time, end_time, accessibility_confirmed?}` |
| GET | `/api/reservations?spot_id=` | List reservations |
| POST | `/api/reservations/<id>/cancel` | Cancel a reservation |
| POST | `/api/reservations/<id>/check-in` | Mark occupied, start billing clock: `{at?}` |
| POST | `/api/reservations/<id>/check-out` | Mark vacated, compute bill: `{at?}` |
| POST | `/api/sensors/occupancy` | Sensor ingestion (real or simulated): `{spot_id, occupied}` |
| GET | `/api/analytics/peak-hour?lot_id=` | Hour-of-day (0-23) with highest occupancy |
| GET | `/api/analytics/average-duration?lot_id=` | Average parked duration (hours) per spot type |

## Tests

18 tests in `tests/`, covering availability filtering, reservation overlap
(same spot rejected, different spot accepted, back-to-back accepted),
handicap-spot confirmation, cancellation freeing a spot, check-in/check-out
billing (including the minimum-charge and rounding rules), simulated sensor
ingestion changing availability counts, and the two analytics functions
against hand-crafted data.

```bash
pytest -v
```

CI (`.github/workflows/tests.yml`) runs the suite on push/PR against Python
3.11 and 3.12.

## License

MIT, see `LICENSE`.
