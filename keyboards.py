"""
Inline keyboard builders.

New in this version:
  • main_menu_keyboard()         — adds Recently Used + Active Numbers + Search buttons
  • search_prompt_keyboard()     — shown after user picks 🔍 Search
  • recently_used_keyboard()     — shown from "Recently Used" menu item
  • active_numbers_keyboard()    — lists all currently active orders for the user
  • active_order_keyboard()      — cancel + refresh buttons for a live order
  • sms_list_keyboard()          — shown alongside received-SMS messages

Kept:
  • countries_keyboard()
  • services_keyboard()          — now accepts optional search_query for filtering
  • cancel_keyboard()
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_MAX_SERVICES_PER_PAGE = 48
_CB_DATA_LIMIT = 64


def _safe_cb(data: str) -> str:
    return data.encode()[:_CB_DATA_LIMIT].decode(errors="ignore")


# ── Main menu ──────────────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Get OTP Number",       callback_data="menu:get_otp")],
        [InlineKeyboardButton("🔍 Search Service",       callback_data="menu:search")],
        [InlineKeyboardButton("🕐 Recently Used",        callback_data="menu:recent")],
        [InlineKeyboardButton("📋 Active Numbers",       callback_data="menu:active")],
        [InlineKeyboardButton("💰 Check Balance",        callback_data="menu:balance")],
    ])


# ── Search ─────────────────────────────────────────────────────────────────────

def search_prompt_keyboard() -> InlineKeyboardMarkup:
    """Shown after user taps Search — tells them to type their query."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back:main")],
    ])


# ── Recently Used ──────────────────────────────────────────────────────────────

def recently_used_keyboard(recent: list[tuple[str, str, str]]) -> InlineKeyboardMarkup:
    """
    recent: list of (service_id, service_name, price) newest-first.
    Each button triggers the same service: flow as a normal service pick.
    """
    buttons: list[list[InlineKeyboardButton]] = []
    for sid, sname, price in recent:
        label = f"🔁 {sname} ₹{price}"
        name_trunc = sname[:40]
        cb = _safe_cb(f"service:{sid}:{name_trunc}")
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])

    buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back:main")])
    return InlineKeyboardMarkup(buttons)


# ── Active numbers ─────────────────────────────────────────────────────────────

def active_numbers_keyboard(orders) -> InlineKeyboardMarkup:
    """orders: list of ActiveOrder objects."""
    buttons: list[list[InlineKeyboardButton]] = []
    for order in orders:
        label = f"📱 +{order.phone} — {order.service_name.title()}"
        cb = _safe_cb(f"view_active:{order.activation_id}")
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])

    if not buttons:
        buttons.append([InlineKeyboardButton("(no active numbers)", callback_data="noop")])

    buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back:main")])
    return InlineKeyboardMarkup(buttons)


def active_order_keyboard(activation_id: str) -> InlineKeyboardMarkup:
    """Buttons shown on the live status message for an active order."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh Status",   callback_data=_safe_cb(f"refresh:{activation_id}")),
            InlineKeyboardButton("❌ Cancel Number",     callback_data=_safe_cb(f"cancel:{activation_id}")),
        ],
        [InlineKeyboardButton("🔙 Back to Menu",         callback_data="back:main")],
    ])


# ── SMS list ───────────────────────────────────────────────────────────────────

def sms_list_keyboard(activation_id: str) -> InlineKeyboardMarkup:
    """Keyboard shown under a multi-SMS update."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Number", callback_data=_safe_cb(f"cancel:{activation_id}"))],
    ])


# ── Countries ──────────────────────────────────────────────────────────────────

def countries_keyboard(countries: dict) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, name in countries.items():
        row.append(InlineKeyboardButton(
            f"🌍 {name}",
            callback_data=_safe_cb(f"country:{code}"),
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ── Services ───────────────────────────────────────────────────────────────────

def services_keyboard(
    services: dict,
    page: int = 0,
    search_query: str = "",
) -> InlineKeyboardMarkup:
    """
    services: {service_id: {service_name, service_price, server_name}, ...}
    search_query: optional filter string (case-insensitive name match)
    Paginated to _MAX_SERVICES_PER_PAGE items per page.
    """
    if search_query:
        q = search_query.lower()
        items = [
            (sid, info) for sid, info in services.items()
            if q in info.get("service_name", "").lower()
        ]
    else:
        items = list(services.items())

    total_pages = max(1, (len(items) + _MAX_SERVICES_PER_PAGE - 1) // _MAX_SERVICES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * _MAX_SERVICES_PER_PAGE
    page_items = items[start: start + _MAX_SERVICES_PER_PAGE]

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for sid, info in page_items:
        name  = info["service_name"][:40]
        label = f"{info['service_name']} ₹{info['service_price']}"
        cb    = _safe_cb(f"service:{sid}:{name}")
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"svcpage:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"svcpage:{page+1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back:countries")])
    return InlineKeyboardMarkup(buttons)


# ── Cancel (single-button, legacy) ────────────────────────────────────────────

def cancel_keyboard(activation_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Number", callback_data=_safe_cb(f"cancel:{activation_id}"))]
    ])
