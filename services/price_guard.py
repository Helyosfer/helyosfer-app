"""The single normalisation boundary for external prices.

WHY A SEPARATE MODULE: prices entered from three different places
(`price_providers`, `asset_service._fetch_live_try_prices`,
`price_service._store_cache`) and all three used the same pattern:

    if value is not None and float(value) > 0:

That pattern ACCEPTS INFINITY -- `float("inf") > 0` is True. Because
`json.loads` parses the `Infinity` and `NaN` constants by default, a broken or
hostile provider response could produce this directly. Once an infinite price
was written to the cache it became persistent and turned the ENTIRE portfolio
total into `inf` via `inf * quantity`.

The check was gathered here rather than written separately at each call site:
three copies drifting apart over time is the same mechanism by which this
defect arose in the first place.

"""

import math

__all__ = ["finite_positive_price"]


def finite_positive_price(value) -> float | None:
    """Returns a `float` if the price is acceptable, otherwise `None`.

    What is rejected, and why:
      * `NaN` / `Inf` / `-Inf` -- the class a `> 0` comparison cannot catch.
        An `inf` produced by overflow (`1e400`) lands here too.
      * `bool` -- a subclass of `int` in Python, so `True` silently passes a
        numeric check. A price is never a bool.
      * zero and negative -- cannot be an asset's market price.
      * `None`, empty text, and anything that will not convert to a number.

    IT NEVER RAISES. Every caller processes a batch result in a loop; dropping
    the whole batch because of one broken symbol would be the very "one bad
    value ruins everything" behaviour this function exists to prevent. The
    broken symbol is skipped and the sound ones pass.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0:
        return None
    return price
