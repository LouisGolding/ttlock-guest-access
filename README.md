# ttlock-guest-access

A single-file Python CLI for giving guests access to [TTLock](https://open.ttlock.com)
smart locks — **without the guest needing the TTLock app, an account, or
anything installed**. Built for and deployed at a real hotel; useful for
short-term rentals, hotels, and Airbnbs.

## Background

A hotel running TTLock smart locks on its 22 guest rooms asked for help with
check-in friction: their process required every guest to receive an eKey
through the TTLock app — meaning each guest had to open an email, create an
account, set a password, and install an app just to get into their room.
They wanted what TTLock's API calls an "unlock link": a URL the guest simply
taps and the door opens.

Getting there meant working through the real constraints of a live
deployment, all diagnosed against the hotel's production account:

- **Hardware reality.** Remote links route internet → TTLock cloud → a WiFi
  gateway box → Bluetooth → lock. Auditing the account showed a single
  gateway covering a handful of locks, while the app "worked everywhere"
  because a phone at the door is its own Bluetooth radio — a distinction the
  owners weren't aware of. The tool surfaces gateway coverage per lock and
  refuses to create links that physically cannot work, offering keypad
  passcodes (which need no gateway) as the fallback.
- **An undocumented API pitfall.** Live testing revealed that TTLock ties
  the unlock link URL to the *recipient account*, not the individual eKey:
  two keys sent to the same account return the **same URL**. A naive
  implementation reusing one holder account would hand every guest a link
  opening every active door. The tool therefore registers a fresh throwaway
  holder account per link, scoping each URL to exactly one key and one door.
- **Operations, not just code.** The people running this day to day are
  front-desk staff, not developers: commands accept room names instead of
  lock IDs, times are interpreted in each lock's own timezone, credentials
  load from a local env file, and every generated key prints its own
  ready-to-paste revocation command for checkout.

The result: one command per guest, a text message with a link, and no app on
the guest's phone. Details identifying the property have been removed.

Two ways in:

- **Guest links** — a `https://.../h?k=...` URL. The guest taps it and the
  door unlocks over the internet. Requires the lock to be connected to a
  TTLock WiFi gateway.
- **Keypad passcodes** — a time-limited PIN typed on the lock's keypad.
  Works on **every** lock, including Bluetooth-only ones with no gateway,
  because the lock computes valid codes itself.

No dependencies — just Python 3 and the standard library.

## Setup

1. Create an application on the [TTLock Open Platform](https://open.ttlock.com)
   (or the [EU platform](https://euopen.ttlock.com)) to get a client ID and
   secret.
2. Copy `ttlock.env.example` to `ttlock.env` and fill in your client ID,
   client secret, and the TTLock account that administers your locks.
3. That's it:

```bash
python3 ttlock.py locks
```

## Usage

`<room>` can be a room number/name matched against your lock aliases
(e.g. `101`, `laundry`, `"room 12"`) or a literal lockId. Times are in the
lock's local timezone.

```bash
# List every lock, its ID, and whether it can do links (gateway) or not
python3 ttlock.py locks

# Guest link, valid for a stay (gateway-connected locks only)
python3 ttlock.py guestlink 101 "2026-07-03 15:00" "2026-07-05 12:00" "Guest name"

# Keypad passcode (works on every lock, gateway or not)
python3 ttlock.py passcode 101 "2026-07-03 15:00" "2026-07-05 12:00" "Guest name"

# Checkout: list keys on a lock, then revoke — the link dies instantly
python3 ttlock.py keys 101
python3 ttlock.py revoke <keyId>

# Gateways on the account
python3 ttlock.py gateways
```

## How the guest link works

`guestlink` registers a fresh throwaway TTLock account (via
`/v3/user/register`), sends it an eKey with `remoteEnable=1`
(`/v3/key/send`), and asks for that key's unlock link
(`/v3/key/getUnlockLink`). The guest only ever sees the URL.

**Why a fresh account per link:** TTLock ties the link URL to the recipient
*account*, not the individual eKey — all keys sent to one account return the
same URL. Reusing a single holder account across guests would hand every
guest a link to every active door. One throwaway account per link keeps
every URL scoped to exactly one key and one door.

## Limitations (TTLock's, not this tool's)

- **Links need a gateway.** The tap goes internet → TTLock cloud → gateway →
  Bluetooth → lock. No gateway in Bluetooth range of the lock means no link,
  ever — the tool refuses to create dead links and tells you to use a
  passcode instead. One gateway (e.g. TTLock G2) covers the locks near it.
- **A link is a key.** Anyone holding the URL can open the door while the
  key is valid. Send it only to the guest, keep validity windows tight, and
  revoke at checkout.
- **Passcode quirks:** validity is rounded to the hour; the code must be
  used at least once within 24 h of its start or the lock cancels it; on
  gateway-less locks a passcode can't be revoked remotely — it just expires.
- Lock timezones come from the lock's own configuration
  (`timezoneRawOffset`). If a lock was set up with the wrong timezone, its
  windows will be shifted — fix it in the TTLock app or pad your times.

## Security notes

- `ttlock.env` holds the master credentials for every door on the account.
  It is gitignored; keep it that way and never send it around in plain text.
- Everything this tool does happens through TTLock's official cloud API with
  your own credentials. There is no local persistence — revocation and
  expiry are enforced by TTLock/the locks themselves.
