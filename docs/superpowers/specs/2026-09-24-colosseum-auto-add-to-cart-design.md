# Colosseum monitor — automatic add-to-cart — design

## Problem

The Colosseum's target time slots have repeatedly opened and closed within
minutes (sometimes seconds) — confirmed directly in `log.txt` and by the
user's own live attempts, which have twice failed to complete in time (once
losing the window entirely, once blocked by a Cloudflare Turnstile failure
unrelated to timing). The user wants the monitor to put the ticket **in the
cart** the moment a target date/time opens, so a human only has to finish
checkout — not race the whole flow from scratch.

## Scope boundary (unchanged from every other monitor in this repo)

The bot stops at "add to cart." It never enters personal or payment
information, never completes checkout, and never attempts to defeat the
Cloudflare Turnstile challenge beyond what a normal browser session already
does. Turnstile failures are treated as an expected possible outcome, not a
bug to route around.

## Confirmed technical findings

- **Participant count starts empty**, not defaulting to 1 — confirmed live
  (this is what originally blocked the user's own manual attempt, surfaced
  as "SELEZIONA ALMENO UN PARTECIPANTE").
- **The "Aggiungi" (add to cart) button is reachable and clickable** once
  participants + date + time are all set — confirmed live, reproduced the
  full flow successfully in a throwaway browser session on 2026-09-23.
- **The real, observed failure mode** for add-to-cart is
  `POST /mtajax/addtocart` returning `403`, tied to a Cloudflare Turnstile
  error (`Error: 600010`) in the user's own browser — confirmed from the
  user's own pasted console log. This is an existing, real risk, not a
  hypothetical.
- **The cart's hold time is not a fixed number anywhere in the site's
  code.** `cart-ui.js` reads `cart.expirationDate` (populated server-side,
  presumably from the `addtocart` response or a follow-up `check_cart`
  call) and counts down to it; on expiry, the page's own JS auto-drops the
  cart and shows an expiry message. There is no constant to hardcode —
  this design deliberately doesn't try to compute or guess the hold
  duration. It watches the cart's own item count instead (see below).
- Nothing about the actual add-to-cart click sequence, the cart-count
  display, or the expiry auto-drop has been exercised against a truly live
  target slot yet (the Colosseum itself is closed today, 2026-09-24,
  following the incident reported on the site — see the closure notice
  found during this session). The first real end-to-end run of this
  feature will be the first time a genuine target slot opens after it
  ships.

## Architecture

Colosseum-only — the other three monitors' checkout flows are entirely
different platforms, not worth generalizing for one site's need right now.

New module `colosseum_monitor/cart.py`:
- `set_participant_count(page, count)` — sets the participant stepper to
  an exact count (reads the field back after each `+` click rather than
  blind-clicking a fixed number of times, since a single click was
  observed jumping the value further than expected in live testing).
- `select_time_slot(page, day_number, time_str)` — reuses the existing
  `click_day()` to open the slot picker, then clicks the specific
  non-disabled radio matching `time_str`.
- `add_to_cart(page)` — clicks "Aggiungi" and determines success or
  failure from the real `/mtajax/addtocart` network response (mirroring
  exactly what the user's own console log showed: `200` vs `403`) rather
  than guessing from DOM state alone.
- `is_cart_empty(page)` — confirmed live (2026-09-24, with an empty cart,
  no populated cart needed to verify this part): elements carrying the
  site's own `hide-empty-cart` class (`#btn-showcart`, the "Procedi"
  checkout button; `.cart-modal-button`, the header cart total) are
  `display: none` right now while the cart is empty. Checks whether
  `#btn-showcart` is visible as the empty/non-empty signal, rather than
  trying to parse an exact item count — the design only ever needs to know
  "is there still something in the cart," not how many.
- `wait_for_cart_to_empty(page, poll_interval_seconds)` — every interval,
  does a genuine page reload (a real navigation, not an injected-script
  fetch — the same WAF-safe principle this whole repo already follows) and
  checks `is_cart_empty()`; returns once it's true, however that happened
  (user finished checkout, or the site's own expiry logic dropped it).

### Data flow (one run where a target slot is newly available)

1. Normal check runs exactly as today: off-screen browser, navigate to the
   target month, read statuses/slots, close that browser.
2. Compare against the previous state (loaded the same way
   `monitor_common.engine` already does) to find newly-available
   (date, time) pairs among the target dates.
3. If `config.AUTO_ADD_TO_CART` is on and at least one such pair exists:
   **pick the earliest date first** (and earliest time within that date as
   the tiebreaker) — per the user's explicit preference, not just
   whichever happens to be found first in iteration order.
4. Open a **second, on-screen** browser (not the off-screen one used for
   the quick check) and re-verify that specific date/time is still open —
   the gap since step 1 is real and slots move fast, so this is a genuine
   re-check, not a formality.
5. If still available: set participants to
   `config.AUTO_ADD_TO_CART_PARTICIPANTS`, select the date/time, click
   add-to-cart.
6. On success: send the urgent notification **immediately** (before
   waiting on anything), then call `wait_for_cart_to_empty()` on this
   browser. Once it returns, log that the cart session ended and close the
   browser.
7. On any failure along the way (slot closed in the re-check, add-to-cart
   itself failed/403'd) — log exactly what happened, close the browser,
   and fall through to today's existing behavior: normal state
   save + "hurry to the site" notification. No half-open state is ever
   left behind.
8. If nothing new is available, or the feature is off: behavior is
   identical to today, byte-for-byte.

### Why a second browser instead of moving the first one

The off-screen position
(`--window-position=-32000,-32000`) exists so the required real (non-headless)
browser doesn't pop up in front of the user on every 5-minute check.
Repositioning an already-running window would need OS-level window
manipulation with no clean Playwright API for it. Launching a second,
separate browser already positioned on-screen only when there's actually
something worth showing is simpler and has no failure mode worse than "one
extra browser launch" on the rare occasion something real is found.

### Notification wording

A new, distinctly urgent message — not the existing
`format_availability_message` — since this is telling the user a cart is
actively held open and waiting, not just that a date opened up. States the
date/time, that a browser window is open on their PC, and that it will
close on its own once the cart empties (checkout or expiry).

## Config additions (`colosseum_monitor/config.py`)

```
AUTO_ADD_TO_CART = True
AUTO_ADD_TO_CART_PARTICIPANTS = 2
CART_POLL_INTERVAL_SECONDS = 30
```

`AUTO_ADD_TO_CART` exists specifically so this can be turned off without a
code change if it misbehaves — flipping one line and committing is safer
than reverting a feature under time pressure.

## Error handling

Same philosophy as the rest of this repo: every failure is logged, none of
them alert (per the earlier decision to only ever alert on real
availability) — except the one deliberate exception, which isn't a
failure: the "your cart is ready, go finish it" message, sent the moment
add-to-cart actually succeeds.

## Testing plan

- Unit tests (fakes, no live network) for the pure decision logic: given a
  previous/current state pair, does it pick the correct (earliest date,
  earliest time) newly-available pair, and does it correctly no-op when
  nothing qualifies.
- Unit tests for `set_participant_count`'s read-back-and-verify loop
  against a fake page.
- The empty/non-empty cart signal (`is_cart_empty`) is already confirmed
  live (see above). What's *not* verifiable without a populated cart —
  the add-to-cart success/failure network response shape, and the expiry
  auto-drop actually firing — can only be confirmed once a real target
  slot is open again, since the Colosseum is closed today. The
  implementation plan will build the success/failure check around the
  exact behavior already observed in the user's own console log
  (`POST /mtajax/addtocart` → `200` or `403`), rather than guessing further.

## Explicit non-goals

- No checkout/payment automation, ever — unchanged from every other
  monitor in this repo.
- No attempt to bypass or work around a Turnstile failure — treated as an
  expected possible outcome, logged and fallen back from.
- Not generalized to the other three monitors.
- No handling of more than one newly-available slot per run beyond picking
  the single best (earliest) one.
