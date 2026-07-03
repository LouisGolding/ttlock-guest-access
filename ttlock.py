#!/usr/bin/env python3
"""
TTLock helper — guest passcodes + remote unlock links.

What this does:
  1. Logs into the TTLock Open Platform (OAuth) with your account.
  2. Lists your locks and shows which ones are ONLINE (a remote unlock
     link only works on locks that are online via a gateway/WiFi).
  3. Generates a time-limited keypad PASSCODE for any lock — this works
     on Bluetooth-only locks too (no gateway needed). Guest just types
     the code on the door keypad.
  4. Generates a remote unlock link (https://c.ttekey.com/h?k=...) —
     ONLY works on online locks whose eKey has remote unlock enabled.

Usage (<room> can be a room number/name like 101, "laundry", "room 12",
or a full lockId; times are in the property's local time):

  python3 ttlock.py locks                 # list all locks + online status
  python3 ttlock.py guestlink <room> "YYYY-MM-DD HH:MM" "YYYY-MM-DD HH:MM" [name]
                                          # GUEST LINK: tap-to-unlock URL,
                                          # guest needs no app/account
                                          # (ONLINE/gateway locks only)
  python3 ttlock.py passcode <room> "YYYY-MM-DD HH:MM" "YYYY-MM-DD HH:MM" [name]
                                          # keypad PIN — works on EVERY lock,
                                          # gateway or not
  python3 ttlock.py keys <room>           # list eKeys on a lock (find keyId)
  python3 ttlock.py revoke <keyId>        # delete an eKey -> kills its link
  python3 ttlock.py link <keyId>          # unlock link for an existing eKey
  python3 ttlock.py gateways              # list gateways on the account

Credentials: fill in the ttlock.env file next to this script (or set the
TTLOCK_* environment variables). Region defaults to the EU server.

Passcode limitations (these come from how TTLock works, not this script):
  - Validity is rounded to the HOUR by TTLock (e.g. 21:25 becomes 21:00).
  - The code must be USED at least once within 24 h of its start time,
    otherwise the lock invalidates it.
  - Deleting a passcode remotely only works on online (gateway) locks;
    on Bluetooth-only locks it simply expires at its end time.
"""

import datetime
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

def _load_env_file():
    """Load credentials from a ttlock.env file next to this script, so the
    tool works without manually exporting environment variables. Real
    environment variables still win if both are set."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ttlock.env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env_file()

# EU server. Use https://api.ttlock.com for the global/other server.
BASE = os.environ.get("TTLOCK_BASE", "https://euapi.ttlock.com")

CLIENT_ID = os.environ.get("TTLOCK_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("TTLOCK_CLIENT_SECRET", "")
USERNAME = os.environ.get("TTLOCK_USERNAME", "")
PASSWORD = os.environ.get("TTLOCK_PASSWORD", "")


def now_ms() -> int:
    return int(time.time() * 1000)


def md5_lower(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().lower()


def post(path: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def get_token() -> dict:
    """OAuth: exchange client creds + account login for an access token."""
    res = post(
        "/oauth2/token",
        {
            "clientId": CLIENT_ID,
            "clientSecret": CLIENT_SECRET,
            "username": USERNAME,
            "password": md5_lower(PASSWORD),
        },
    )
    if "access_token" not in res:
        raise SystemExit(f"Login failed: {json.dumps(res)}")
    return res


def list_locks(token: str) -> list:
    res = post(
        "/v3/lock/list",
        {
            "clientId": CLIENT_ID,
            "accessToken": token,
            "pageNo": 1,
            "pageSize": 100,
            "date": now_ms(),
        },
    )
    return res.get("list", []) if isinstance(res, dict) else []


def lock_detail(token: str, lock_id: int) -> dict:
    return post(
        "/v3/lock/detail",
        {
            "clientId": CLIENT_ID,
            "accessToken": token,
            "lockId": lock_id,
            "date": now_ms(),
        },
    )


def list_keys(token: str, lock_id: int) -> dict:
    return post(
        "/v3/lock/listKey",
        {
            "clientId": CLIENT_ID,
            "accessToken": token,
            "lockId": lock_id,
            "pageNo": 1,
            "pageSize": 100,
            "date": now_ms(),
        },
    )


def list_gateways(token: str) -> dict:
    return post(
        "/v3/gateway/list",
        {
            "clientId": CLIENT_ID,
            "accessToken": token,
            "pageNo": 1,
            "pageSize": 100,
            "date": now_ms(),
        },
    )


def gateways_for_lock(token: str, lock_id: int) -> dict:
    return post(
        "/v3/gateway/listByLock",
        {
            "clientId": CLIENT_ID,
            "accessToken": token,
            "lockId": lock_id,
            "date": now_ms(),
        },
    )


def get_passcode(token: str, lock_id: int, start_ms: int, end_ms: int,
                 name: str = "") -> dict:
    """Server-generated keypad passcode (type 3 = valid for a period).

    Works on Bluetooth-only locks: the code comes from an algorithm the
    lock already knows, so nothing needs to be pushed to the door.
    """
    params = {
        "clientId": CLIENT_ID,
        "accessToken": token,
        "lockId": lock_id,
        "keyboardPwdType": 3,
        "startDate": start_ms,
        "endDate": end_ms,
        "date": now_ms(),
    }
    if name:
        params["keyboardPwdName"] = name
    return post("/v3/keyboardPwd/get", params)


def unlock_link(token: str, key_id: int) -> dict:
    return post(
        "/v3/key/getUnlockLink",
        {
            "clientId": CLIENT_ID,
            "accessToken": token,
            "keyId": key_id,
            "date": now_ms(),
        },
    )


def register_guest_user() -> str:
    """Create a throwaway TTLock account to hold ONE guest's eKey.

    IMPORTANT: the unlock link is tied to the recipient ACCOUNT, not the
    key — all keys sent to the same account share one link. So every guest
    must get their own account, or they'd all receive the same URL opening
    every active door.
    """
    import secrets
    username = f"lk{int(time.time())}{secrets.token_hex(2)}"
    res = post(
        "/v3/user/register",
        {
            "clientId": CLIENT_ID,
            "clientSecret": CLIENT_SECRET,
            "username": username,
            "password": md5_lower(secrets.token_hex(16)),
            "date": now_ms(),
        },
    )
    if "username" not in res:
        raise SystemExit(f"Could not create guest account: {json.dumps(res)}")
    return res["username"]


def send_key(token: str, lock_id: int, receiver: str, start_ms: int,
             end_ms: int, key_name: str) -> dict:
    """Send an eKey with remote unlock ENABLED (required for links).

    receiver = the guest's TTLock account: email, or phone number in
    international format (e.g. +12125551234).
    """
    return post(
        "/v3/key/send",
        {
            "clientId": CLIENT_ID,
            "accessToken": token,
            "lockId": lock_id,
            "receiverUsername": receiver,
            "keyName": key_name,
            "startDate": start_ms,
            "endDate": end_ms,
            "remoteEnable": 1,
            "date": now_ms(),
        },
    )


def cmd_locks(token: str):
    locks = list_locks(token)
    if not locks:
        print("No locks found on this account.")
        return
    print(f"Found {len(locks)} lock(s):\n")
    for lk in locks:
        lock_id = lk.get("lockId")
        detail = lock_detail(token, lock_id)
        has_gateway = detail.get("hasGateway", 0)
        online = "ONLINE (link will work)" if has_gateway else "Bluetooth-only (remote link will NOT work)"
        print(f"  Lock ID : {lock_id}")
        print(f"  Name    : {lk.get('lockName')}")
        print(f"  Alias   : {lk.get('lockAlias')}")
        print(f"  Status  : {online}")
        print("  " + "-" * 40)


def resolve_lock(token: str, text: str) -> int:
    """Turn a room name/number (e.g. '101', 'laundry', 'room 12') into a
    lockId. A long all-digit value is treated as a literal lockId."""
    if text.isdigit() and len(text) >= 6:
        return int(text)
    locks = list_locks(token)
    needle = text.lower().strip()
    matches = [
        lk for lk in locks
        if needle in ((lk.get("lockAlias") or lk.get("lockName") or "").lower())
    ]
    if len(matches) == 1:
        lk = matches[0]
        print(f"[ok] '{text}' -> {lk.get('lockAlias') or lk.get('lockName')} "
              f"(lockId {lk['lockId']})")
        return lk["lockId"]
    if not matches:
        raise SystemExit(
            f"No lock matches '{text}'. Run 'python3 ttlock.py locks' to see "
            "all rooms."
        )
    listing = "\n".join(
        f"  {lk['lockId']}  {lk.get('lockAlias') or lk.get('lockName')}"
        for lk in matches
    )
    raise SystemExit(f"'{text}' matches several locks — be more specific:\n{listing}")


def parse_when(text: str) -> datetime.datetime:
    """Accept 'YYYY-MM-DD HH:MM' (or with seconds) as naive wall-clock time."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise SystemExit(f"Can't parse time '{text}'. Use format: YYYY-MM-DD HH:MM")


def lock_window(detail: dict, start_text: str, end_text: str):
    """Convert wall-clock start/end (in the LOCK's timezone, i.e. the
    property's local time) to epoch milliseconds, using the offset stored
    on the lock."""
    offset_ms = detail.get("timezoneRawOffset")
    start_naive = parse_when(start_text)
    end_naive = parse_when(end_text)
    if offset_ms is not None:
        epoch = datetime.timezone.utc
        start_ms = int(start_naive.replace(tzinfo=epoch).timestamp() * 1000) - offset_ms
        end_ms = int(end_naive.replace(tzinfo=epoch).timestamp() * 1000) - offset_ms
        hours = offset_ms / 3600000
        tz_note = f"lock timezone (UTC{hours:+g})"
    else:
        start_ms = int(start_naive.timestamp() * 1000)
        end_ms = int(end_naive.timestamp() * 1000)
        tz_note = "this computer's timezone (lock reported no timezone)"
    if end_ms <= start_ms:
        raise SystemExit("End time must be after start time.")
    return start_ms, end_ms, tz_note


def cmd_passcode(token: str, lock_id: int, start_text: str, end_text: str,
                 name: str = ""):
    detail = lock_detail(token, lock_id)
    lock_name = detail.get("lockAlias") or detail.get("lockName") or str(lock_id)
    start_ms, end_ms, tz_note = lock_window(detail, start_text, end_text)

    res = get_passcode(token, lock_id, start_ms, end_ms, name)
    code = res.get("keyboardPwd")
    if not code:
        raise SystemExit(f"Passcode request failed: {json.dumps(res)}")

    print(f"Lock      : {lock_name} (lockId {lock_id})")
    print(f"PASSCODE  : {code}")
    print(f"Valid     : {start_text}  ->  {end_text}  [{tz_note}]")
    print(f"            (TTLock rounds validity to the hour)")
    print()
    print("Guest instructions: on the door keypad, type the code then press")
    print("the # / unlock key at the bottom. Must be used at least once")
    print("within 24 h of the start time or the lock cancels it.")


def cmd_keys(token: str, lock_id: int):
    res = list_keys(token, lock_id)
    items = res.get("list", [])
    if not items:
        print("No eKeys on this lock.")
        return
    offset_ms = lock_detail(token, lock_id).get("timezoneRawOffset")
    tz = (datetime.timezone(datetime.timedelta(milliseconds=offset_ms))
          if offset_ms is not None else None)
    print(f"{len(items)} eKey(s) on this lock"
          + (" (times shown in the lock's local time):" if tz else ":") + "\n")
    for k in items:
        if k.get("endDate"):
            start = datetime.datetime.fromtimestamp(k.get("startDate", 0) / 1000, tz)
            end = datetime.datetime.fromtimestamp(k.get("endDate", 0) / 1000, tz)
            valid = f"{start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M}"
        else:
            valid = "permanent"
        remote = "yes" if k.get("remoteEnable") == 1 else "no"
        holder = k.get("username", "?")
        # Throwaway link-holder accounts made by this tool look like
        # '<appprefix>_lk<timestamp><hex>'
        is_link = "_lk1" in holder
        print(f"  keyId   : {k.get('keyId')}"
              + ("   <-- link key (made by this tool)" if is_link else ""))
        print(f"  name    : {k.get('keyName')}")
        print(f"  holder  : {holder}")
        print(f"  remote  : {remote}")
        print(f"  valid   : {valid}")
        print(f"  revoke  : python3 ttlock.py revoke {k.get('keyId')}")
        print("  " + "-" * 40)


def cmd_link(token: str, key_id: int):
    res = unlock_link(token, key_id)
    print(json.dumps(res, indent=2))


def cmd_guestlink(token: str, lock_id: int,
                  start_text: str, end_text: str, name: str = ""):
    """Full flow: fresh holder account -> remote-enabled eKey -> link.

    A NEW throwaway account is created for every link because TTLock ties
    the link URL to the recipient account (all keys on one account share
    one link). The guest never sees or needs this account.
    """
    detail = lock_detail(token, lock_id)
    lock_name = detail.get("lockAlias") or detail.get("lockName") or str(lock_id)

    if not detail.get("hasGateway"):
        raise SystemExit(
            f"'{lock_name}' has NO gateway — a remote unlock link cannot work "
            "on this lock. Use the 'passcode' command instead, or install a "
            "TTLock gateway near this room first."
        )

    start_ms, end_ms, tz_note = lock_window(detail, start_text, end_text)

    receiver = register_guest_user()
    print(f"[ok] Created key-holder account {receiver}")

    res = send_key(token, lock_id, receiver, start_ms, end_ms,
                   name or f"Guest link {lock_name}")
    key_id = res.get("keyId")
    if not key_id:
        raise SystemExit(f"Sending the eKey failed: {json.dumps(res)}")
    print(f"[ok] eKey sent (keyId {key_id}, remote unlock ON)")

    link_res = unlock_link(token, key_id)
    link = link_res.get("link")
    if not link:
        raise SystemExit(
            f"eKey was sent, but the link was refused: {json.dumps(link_res)}\n"
            "Most likely 'remote unlock' is not enabled on the LOCK itself — "
            "turn it on in the TTLock app (lock settings, done at the door "
            "via Bluetooth), then rerun:  python3 ttlock.py link "
            f"{key_id}"
        )

    print()
    print(f"Lock   : {lock_name} (lockId {lock_id})")
    print(f"LINK   : {link}")
    print(f"Valid  : {start_text}  ->  {end_text}  [{tz_note}]")
    print(f"Revoke : python3 ttlock.py revoke {key_id}")
    print()
    print("Send the link to the guest — tapping it unlocks the door remotely.")


def cmd_revoke(token: str, key_id: int):
    res = post(
        "/v3/key/delete",
        {
            "clientId": CLIENT_ID,
            "accessToken": token,
            "keyId": key_id,
            "date": now_ms(),
        },
    )
    if res.get("errcode") == 0:
        print(f"[ok] eKey {key_id} deleted — its link is now dead.")
    else:
        raise SystemExit(f"Revoke failed: {json.dumps(res)}")


def main():
    if not all([CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD]):
        raise SystemExit(
            "Missing credentials. Fill in the ttlock.env file next to this "
            "script (or set TTLOCK_CLIENT_ID, TTLOCK_CLIENT_SECRET, "
            "TTLOCK_USERNAME, TTLOCK_PASSWORD in the environment)."
        )
    args = sys.argv[1:]
    cmd = args[0] if args else "locks"

    tok = get_token()
    token = tok["access_token"]
    print(f"[ok] Logged in. uid={tok.get('uid')} token expires in "
          f"{tok.get('expires_in')} s\n")

    if cmd == "locks":
        cmd_locks(token)
    elif cmd == "passcode":
        if len(args) < 4:
            raise SystemExit(
                'Usage: python3 ttlock.py passcode <room> '
                '"YYYY-MM-DD HH:MM" "YYYY-MM-DD HH:MM" [name]'
            )
        cmd_passcode(token, resolve_lock(token, args[1]), args[2], args[3],
                     args[4] if len(args) > 4 else "")
    elif cmd == "keys":
        if len(args) < 2:
            raise SystemExit("Usage: python3 ttlock.py keys <room>")
        cmd_keys(token, resolve_lock(token, args[1]))
    elif cmd == "link":
        cmd_link(token, int(args[1]))
    elif cmd == "guestlink":
        if len(args) < 4:
            raise SystemExit(
                'Usage: python3 ttlock.py guestlink <room> '
                '"YYYY-MM-DD HH:MM" "YYYY-MM-DD HH:MM" [name]'
            )
        cmd_guestlink(token, resolve_lock(token, args[1]), args[2], args[3],
                      args[4] if len(args) > 4 else "")
    elif cmd == "revoke":
        cmd_revoke(token, int(args[1]))
    elif cmd == "gateways":
        print(json.dumps(list_gateways(token), indent=2))
    else:
        raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
