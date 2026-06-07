"""
checkers.py

NOTE: The Myntra Checker and Swiggy Checker features have been removed
as per the v2 feature update requirements.

This file is kept as a placeholder so existing imports don't break.
All functions raise NotImplementedError — they should not be called.
The SPECIAL_SERVICES config key has also been removed from config.py.
"""


async def is_swiggy_unregistered(phone: str) -> bool:
    raise NotImplementedError("Swiggy Checker has been removed.")


async def is_myntra_unregistered(phone: str) -> bool:
    raise NotImplementedError("Myntra Checker has been removed.")
