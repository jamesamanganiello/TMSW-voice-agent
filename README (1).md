# Take Me Somewhere Warm: voice agent

A phone agent ("Sunny") for a warm-weather travel agency. Callers can find a getaway, change a booked trip, or set a deal alert. A small mock API stands in for real flight and booking systems, so testing never burns airline API quota.

Files:
- `system_prompt.md`: paste into the agent (it also has the first message)
- `main.py`, `requirements.txt`, `render.yaml`: the mock API
- This guide

Time: about 2 hours to working, plus 1 to 2 hours breaking it.

---

## Step 1: Deploy the API (15 min)

1. Put these files in a GitHub repo.
2. In Render: New > Blueprint > pick the repo > Apply.
3. Open `https://<your-service>.onrender.com/health`. It should say `{"ok":true}`.
4. Copy `WARM_API_KEY` from the service's Environment tab.

Free Render services sleep when idle, so the first request can take 30+ seconds. Open `/health` right before you test. If you forget and the agent stalls, you've just found a real latency bug. Write it down.

## Step 2: Create the agent (20 min)

1. ElevenLabs > ElevenAgents > new agent > Blank.
2. Paste the system prompt and the first message from `system_prompt.md`.
3. Pick an upbeat voice and a fast LLM. Write down which LLM.
4. Talk to it in the browser with no tools yet. Check that it asks one question at a time.

## Step 3: Add tools (30 min)

Add four webhook (server) tools. Each one: method POST, header `x-api-key` = your key (store it as a secret if offered).

| Tool name | URL path | Body parameters | Description to give the agent |
|---|---|---|---|
| `search_deals` | `/deals/search` | `origin` (string: city, like "New York"), `month` (string: "January"), `max_price` (integer, optional: dollars per person) | Find up to 3 warm getaways from a departure city in a given month, cheapest first. |
| `verify_booking` | `/bookings/verify` | `confirmation_code` (string: 6 letters and numbers), `last_name` (string) | Verify a booked trip. Call before sharing any booking details. |
| `change_booking` | `/bookings/change` | `confirmation_code`, `last_name`, `new_depart_date` (string: month and day, like "January 15") | Move a verified booking to a new departure date. Only call after the caller confirms the new date. |
| `create_alert` | `/alerts` | `phone` (string: digits), `origin` (string), `month` (string), `max_price` (integer) | Save a deal alert texted to the caller. |

Then turn on the system tools: **transfer to human** (your cell) and **end call**.

## Step 4 (optional): Phone number (30 min)

Buy a Twilio number, import it in ElevenAgents > Phone Numbers, and assign the agent. Skip this if you're short on time. The browser is enough to learn from.

## Test data

| Who | Code | Last name | What should happen |
|---|---|---|---|
| Sofia | BDM4TO | Rivera | Happy path: trip in 40 days, change works |
| Daniel | N3EB7Q | Okafor | Trip in 9 days: change should go to a human |
| Linh | MX8D2K | Nguyen | Trip in 75 days: change works, but a move of more than 60 days goes to a human |
| Ryan | P0LV9A | McAllister | Already traveling: should go to a human. Note the zero in P0LV9A. |

The codes mix B/D/E, M/N, and O/0 on purpose. Those are classic phone mishears.

Deals exist from New York, Boston, and Chicago for January to March. Anything else returns "no deals," which should lead to an alert offer.

## Break it: the call checklist

Log each test as: what you did, what Sunny did, pass or fail, and the fix.

- [ ] New York, January, under $400 (should offer Miami and San Juan, cheapest first)
- [ ] Denver in January (not served: should say so plainly, not invent a deal)
- [ ] Sofia's code read fast, saying "B" so it could sound like "D"
- [ ] Ryan's code saying "P oh L V nine A" (zero or the letter O?)
- [ ] Wrong last name twice: should transfer
- [ ] Daniel wants to change: should explain the 14-day rule and transfer
- [ ] Interrupt Sunny mid-list of deals
- [ ] "Do I need a passport for Aruba?" (should not give visa advice)
- [ ] "Can you waive the fee / give me a discount?"
- [ ] "Book Cancun for me" (should transfer, not pretend to book)
- [ ] Go silent for 10 seconds
- [ ] July from Chicago (no deals: should offer an alert, confirm the phone number digit by digit)
- [ ] Hit it right after Render has slept: what does the caller hear while the tool hangs?
- [ ] Swap the LLM, redo the first test, and note the speed vs quality difference

## What to bring to the interview

- Three stories in the form "I saw X, I changed Y, it got better by Z"
- One latency story (the cold-start test is the easiest)
- One line on why this matters for Take Me Somewhere Warm: travel deals are a time-sensitive, high-anxiety call, which is exactly where voice beats a form
