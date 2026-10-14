# Connecting and pairing

A ZeroClaw gateway with pairing on (the default) answers only clients that
send a paired bearer token: `Authorization: Bearer zc_<64 hex>`. A client
gets one by exchanging a six-digit pairing code, which is single use and
valid for ten minutes.

## Getting a code

- **First run:** the daemon prints a code when it starts and no client is
  paired yet; [`client.pairing.initial_code()`](../reference/endpoints.md)
  also returns it until the first pairing.
- **From a paired client:** `client.pairing.new_code()` mints one for another
  device.
- **On the gateway host:** `client.pairing.admin_code()` and
  `client.pairing.admin_new_code(rotate)` (loopback only); `rotate` can also
  revoke every token (`"all"`) or one device's.

## Exchanging it

```python
async with Client("http://127.0.0.1:42617") as anonymous:
    paired = await anonymous.pairing.pair("123456", "billing-service", "server")
    # Store paired.token as a secret; it is shown only once.
    client = anonymous.with_token(paired.token)
```

`with_token` returns a client for the same gateway that shares the
connection pool. A wrong or expired code is refused with 400; too many
attempts are rate-limited with 429 (`is_rate_limited(err)`), with a
`retry_after` field in the error body (`APIError.body`).

## Managing devices

`client.pairing.devices()` lists the paired devices, `revoke_device(id)`
revokes one and its token, and `rotate_device_token(id)` revokes it and
mints a code for it to pair again.

## Keeping the token safe

The client never prints its token: `repr(client)` shows only the base URL
and whether it is authenticated, and `Paired` leaves the token out of its
`repr` and `str` too. The token never appears in an error or a URL.
