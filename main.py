"""Mock travel API for the Take Me Somewhere Warm voice agent.

Run locally:  uvicorn main:app --reload
Deploy:       Render Blueprint (render.yaml), or any Python host.

Endpoints (all need the x-api-key header except /health):
  POST /deals/search      find warm getaways (no login needed)
  POST /bookings/verify   confirmation code + last name -> booking
  POST /bookings/change   move a booking to new dates (rules apply)
  POST /alerts            save a deal alert for a caller
"""
import os
import re
import uuid
from datetime import date, timedelta

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

API_KEY = os.environ.get("WARM_API_KEY", "dev-key-change-me")
TODAY = date.today()  # bookings are placed relative to server start


def today() -> date:
    return date.today()

app = FastAPI(title="Take Me Somewhere Warm (mock)")

# ---------- Deals: no real airline data, so tests never burn API quota ----------

CITY_TO_AIRPORT = {
    "new york": "NYC", "nyc": "NYC", "jfk": "NYC", "laguardia": "NYC", "newark": "NYC",
    "boston": "BOS", "bos": "BOS",
    "chicago": "CHI", "chi": "CHI", "ohare": "CHI", "o'hare": "CHI",
}

DEALS = [
    # origin, destination, country, month, nights, price per person (USD), avg high (F)
    ("NYC", "San Juan", "Puerto Rico", 1, 4, 389, 83),
    ("NYC", "Cancun", "Mexico", 1, 5, 612, 82),
    ("NYC", "Miami", "USA", 1, 3, 298, 76),
    ("NYC", "Aruba", "Aruba", 2, 5, 749, 86),
    ("NYC", "Punta Cana", "Dominican Republic", 2, 5, 575, 84),
    ("NYC", "Key West", "USA", 2, 4, 520, 76),
    ("NYC", "Tulum", "Mexico", 3, 6, 690, 85),
    ("BOS", "Nassau", "Bahamas", 1, 4, 545, 79),
    ("BOS", "Fort Lauderdale", "USA", 2, 3, 275, 77),
    ("BOS", "Montego Bay", "Jamaica", 2, 5, 680, 86),
    ("CHI", "Cabo San Lucas", "Mexico", 1, 5, 640, 79),
    ("CHI", "Phoenix", "USA", 2, 3, 310, 72),
    ("CHI", "Honolulu", "USA", 3, 7, 1180, 81),
]

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}

# ---------- Bookings: codes chosen to trip up speech recognition ----------
# B vs D vs E, M vs N, 0 vs O are classic mishears on a phone line.

BOOKINGS = {
    "BDM4TO": {"last_name": "Rivera", "first_name": "Sofia", "destination": "San Juan",
               "depart": TODAY + timedelta(days=40), "nights": 4, "travelers": 2},
    "N3EB7Q": {"last_name": "Okafor", "first_name": "Daniel", "destination": "Cancun",
               "depart": TODAY + timedelta(days=9), "nights": 5, "travelers": 1},   # too close to change
    "MX8D2K": {"last_name": "Nguyen", "first_name": "Linh", "destination": "Aruba",
               "depart": TODAY + timedelta(days=75), "nights": 5, "travelers": 4},
    "P0LV9A": {"last_name": "McAllister", "first_name": "Ryan", "destination": "Tulum",
               "depart": TODAY - timedelta(days=3), "nights": 6, "travelers": 2},   # already traveling
}

FREE_CHANGE_DAYS = 14   # changes inside this window need a human agent
MAX_SHIFT_DAYS = 60     # new date must be within this many days of the original

ALERTS: list[dict] = []


def check_key(key: str | None) -> None:
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def norm_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def find_booking(code: str, last_name: str) -> tuple[str, dict] | None:
    code = norm_code(code)
    b = BOOKINGS.get(code)
    if b and b["last_name"].lower() == last_name.strip().lower():
        return code, b
    return None


def parse_date(text: str) -> date | None:
    """Accept '2027-01-15' or spoken-style 'January 15' / 'jan 15th'.

    Callers never say the year, and the model may not know it, so a month + day
    is rolled forward to its next occurrence.
    """
    text = text.strip().lower()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    m = re.match(r"([a-z]+)\.?\s+(\d{1,2})(st|nd|rd|th)?$", text)
    if not m:
        return None
    month = next((n for name, n in MONTHS.items() if name.startswith(m.group(1)[:3])), None)
    if not month:
        return None
    day = int(m.group(2))
    for year in (today().year, today().year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d > today():
            return d
    return None


def booking_view(code: str, b: dict) -> dict:
    return {
        "confirmation_code": code,
        "first_name": b["first_name"],
        "destination": b["destination"],
        "depart_date": b["depart"].isoformat(),
        "return_date": (b["depart"] + timedelta(days=b["nights"])).isoformat(),
        "travelers": b["travelers"],
        "days_until_departure": (b["depart"] - today()).days,
    }


# ---------- Request models ----------

class SearchRequest(BaseModel):
    origin: str
    month: str
    max_price: int | None = None


class VerifyRequest(BaseModel):
    confirmation_code: str
    last_name: str


class ChangeRequest(BaseModel):
    confirmation_code: str
    last_name: str
    new_depart_date: str   # "January 15" or YYYY-MM-DD


class AlertRequest(BaseModel):
    phone: str
    origin: str
    month: str
    max_price: int


# ---------- Endpoints ----------

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/deals/search")
def search_deals(req: SearchRequest, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    origin = CITY_TO_AIRPORT.get(req.origin.strip().lower(), req.origin.strip().upper())
    month = MONTHS.get(req.month.strip().lower())
    if origin not in {"NYC", "BOS", "CHI"}:
        return {"found": False, "reason": "We only fly from New York, Boston, and Chicago right now."}
    if not month:
        return {"found": False, "reason": "I need a month, like January or February."}
    hits = [d for d in DEALS if d[0] == origin and d[3] == month
            and (req.max_price is None or d[5] <= req.max_price)]
    hits.sort(key=lambda d: d[5])
    if not hits:
        return {"found": False, "reason": "No deals match that month and budget. A price alert can catch new ones."}
    return {"found": True, "deals": [
        {"destination": d[1], "country": d[2], "nights": d[4],
         "price_per_person_usd": d[5], "avg_high_f": d[6]}
        for d in hits[:3]]}


@app.post("/bookings/verify")
def verify_booking(req: VerifyRequest, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    found = find_booking(req.confirmation_code, req.last_name)
    if not found:
        return {"verified": False, "reason": "No booking matches that code and last name."}
    return {"verified": True, "booking": booking_view(*found)}


@app.post("/bookings/change")
def change_booking(req: ChangeRequest, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    found = find_booking(req.confirmation_code, req.last_name)
    if not found:
        return {"changed": False, "reason": "No booking matches that code and last name."}
    code, b = found
    days_out = (b["depart"] - today()).days
    if days_out < 0:
        return {"changed": False, "needs_human": True, "reason": "This trip has already started. A travel specialist has to handle changes."}
    if days_out < FREE_CHANGE_DAYS:
        return {"changed": False, "needs_human": True,
                "reason": f"Trips less than {FREE_CHANGE_DAYS} days out need a travel specialist to change."}
    new_depart = parse_date(req.new_depart_date)
    if not new_depart:
        return {"changed": False, "reason": "I couldn't read that date. Ask for a month and day, like January 15."}
    if new_depart <= today() + timedelta(days=FREE_CHANGE_DAYS):
        return {"changed": False, "reason": f"The new date has to be more than {FREE_CHANGE_DAYS} days from today."}
    if abs((new_depart - b["depart"]).days) > MAX_SHIFT_DAYS:
        return {"changed": False, "needs_human": True,
                "reason": f"Moves of more than {MAX_SHIFT_DAYS} days need a travel specialist."}
    b["depart"] = new_depart
    return {"changed": True, "change_fee_usd": 0, "booking": booking_view(code, b)}


@app.post("/alerts")
def create_alert(req: AlertRequest, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    origin = CITY_TO_AIRPORT.get(req.origin.strip().lower(), req.origin.strip().upper())
    month = MONTHS.get(req.month.strip().lower())
    if origin not in {"NYC", "BOS", "CHI"} or not month:
        return {"created": False, "reason": "I need a departure city we serve and a month."}
    alert_id = "ALR-" + uuid.uuid4().hex[:4].upper()
    ALERTS.append({"id": alert_id, "phone": "".join(c for c in req.phone if c.isdigit()),
                   "origin": origin, "month": month, "max_price": req.max_price})
    return {"created": True, "alert_id": alert_id,
            "message": "We'll text this number when a deal under that price shows up."}
