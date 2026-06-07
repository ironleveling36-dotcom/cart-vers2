"""
OTPCart Telegram Bot — main entry point.

Features in this version:
  1.  🔍 Search service by name (inline text filter over the service list)
  2.  🕐 Recently Used Services  — last 5 purchased, one-tap reorder
  3.  📨 Multi-SMS Support        — keep number alive, stream every incoming SMS
  4.  ✂️  Myntra/Swiggy checkers  — REMOVED completely
  5.  ⏰ Auto-Cancel              — no OTP in 5 min → auto-cancel & notify
  6.  📋 Active Number Management — "Active Numbers" menu, view status any time
  7.  💬 OTP After Cancel Request — if OTP lands during cancel, still show it
  8.  ⚡ Real-Time SMS Monitoring — poll every 2 s, instant user notification
  9.  🐛 Bug fixes                — sync, stability, UI, order management
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

import otp_api
import storage
from keyboards import (
    countries_keyboard,
    services_keyboard,
    cancel_keyboard,
    main_menu_keyboard,
    search_prompt_keyboard,
    recently_used_keyboard,
    active_numbers_keyboard,
    active_order_keyboard,
    sms_list_keyboard,
)
from config import BOT_TOKEN, OTP_TIMEOUT

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── State keys stored in ctx.user_data ────────────────────────────────────────
_K_COUNTRY  = "country"
_K_SERVICES = "services"
_K_AWAITING_SEARCH = "awaiting_search"   # bool: next text message is a search query


# ══════════════════════════════════════════════════════════════════════════════
# Commands
# ══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data[_K_AWAITING_SEARCH] = False
    await update.message.reply_text(
        "👋 *Welcome to OTPCart!*\n\n"
        "Powered by OTPDoctor. Choose an option below.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def balance_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        bal = await otp_api.get_balance()
        await update.message.reply_text(
            f"💰 *Balance:* ₹{bal}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Text message handler (used for search query input)
# ══════════════════════════════════════════════════════════════════════════════

async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Intercepts plain text messages when the bot is waiting for a search query."""
    if not ctx.user_data.get(_K_AWAITING_SEARCH):
        # Not waiting for search — ignore or fall through to /start hint
        await update.message.reply_text(
            "Use /start to open the menu.",
            reply_markup=main_menu_keyboard(),
        )
        return

    ctx.user_data[_K_AWAITING_SEARCH] = False
    query = update.message.text.strip()
    country_code = ctx.user_data.get(_K_COUNTRY, "in")

    if not query:
        await update.message.reply_text("⚠️ Empty search query. Try again.")
        return

    # Fetch/use cached services
    services = ctx.user_data.get(_K_SERVICES)
    if not services:
        try:
            services = await otp_api.get_services(country_code)
            ctx.user_data[_K_SERVICES] = services
        except Exception as e:
            await update.message.reply_text(f"❌ Could not load services: {e}")
            return

    kb = services_keyboard(services, page=0, search_query=query)
    await update.message.reply_text(
        f"🔍 *Search results for* `{query}`:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Callback router
# ══════════════════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data: str = query.data
    user_id = query.from_user.id

    # ── Main menu ──────────────────────────────────────────────────────────────
    if data == "menu:get_otp":
        await show_countries(query, ctx)

    elif data == "menu:balance":
        try:
            bal = await otp_api.get_balance()
            await query.edit_message_text(
                f"💰 *Balance:* ₹{bal}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ {e}", reply_markup=main_menu_keyboard())

    # ── Search ────────────────────────────────────────────────────────────────
    elif data == "menu:search":
        ctx.user_data[_K_AWAITING_SEARCH] = True
        # Preload services in background so search is instant
        country_code = ctx.user_data.get(_K_COUNTRY, "in")
        if _K_SERVICES not in ctx.user_data:
            try:
                services = await otp_api.get_services(country_code)
                ctx.user_data[_K_SERVICES] = services
            except Exception:
                pass
        await query.edit_message_text(
            "🔍 *Search for a service*\n\n"
            "Type the service name (e.g. `WhatsApp`, `Google`, `Jio`):",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=search_prompt_keyboard(),
        )

    # ── Recently Used ─────────────────────────────────────────────────────────
    elif data == "menu:recent":
        recent = await storage.get_recently_used(user_id)
        if not recent:
            await query.edit_message_text(
                "🕐 *Recently Used*\n\nYou haven't purchased any services yet.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
        else:
            await query.edit_message_text(
                "🕐 *Recently Used Services*\n\nTap to reorder instantly:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=recently_used_keyboard(recent),
            )

    # ── Active Numbers ────────────────────────────────────────────────────────
    elif data == "menu:active":
        orders = await storage.get_all_active_orders(user_id)
        live_orders = [o for o in orders if not o.is_cancelled and not o.is_expired]
        await query.edit_message_text(
            "📋 *Active Numbers*\n\nTap a number to see its status:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=active_numbers_keyboard(live_orders),
        )

    # ── View active order ──────────────────────────────────────────────────────
    elif data.startswith("view_active:"):
        activation_id = data.split(":", 1)[1]
        order = await storage.get_active_order(user_id, activation_id)
        if not order:
            await query.edit_message_text(
                "⚠️ Order not found or already closed.",
                reply_markup=main_menu_keyboard(),
            )
            return
        text = _format_order_status(order)
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=active_order_keyboard(activation_id),
        )

    # ── Refresh active order ───────────────────────────────────────────────────
    elif data.startswith("refresh:"):
        activation_id = data.split(":", 1)[1]
        order = await storage.get_active_order(user_id, activation_id)
        if not order:
            await query.edit_message_text(
                "⚠️ Order not found or already closed.",
                reply_markup=main_menu_keyboard(),
            )
            return
        # Pull fresh status
        resp = await otp_api.check_status(activation_id)
        new_texts = otp_api.parse_sms_from_status(resp)
        for text in new_texts:
            if not any(m.text == text for m in order.sms_messages):
                order.sms_messages.append(
                    storage.SmsMessage(index=len(order.sms_messages) + 1, text=text)
                )
        text = _format_order_status(order)
        try:
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=active_order_keyboard(activation_id),
            )
        except BadRequest:
            pass  # message unchanged

    # ── Country select ────────────────────────────────────────────────────────
    elif data.startswith("country:"):
        country_code = data.split(":", 1)[1]
        ctx.user_data[_K_COUNTRY] = country_code
        await show_services(query, ctx, country_code, page=0)

    # ── Service select ────────────────────────────────────────────────────────
    elif data.startswith("service:"):
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.edit_message_text("❌ Invalid service selection.")
            return
        _, service_id, service_name = parts
        ctx.user_data["service_id"]   = service_id
        ctx.user_data["service_name"] = service_name.lower()
        await handle_service(query, ctx)

    # ── Pagination ────────────────────────────────────────────────────────────
    elif data.startswith("svcpage:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        country_code = ctx.user_data.get(_K_COUNTRY, "in")
        await show_services(query, ctx, country_code, page=page)

    # ── Cancel number ─────────────────────────────────────────────────────────
    elif data.startswith("cancel:"):
        activation_id = data.split(":", 1)[1]
        order = await storage.get_active_order(user_id, activation_id)
        if order:
            # Mark cancel requested BEFORE sending API call
            # so that if OTP lands during the call, the monitor loop still shows it
            await storage.update_order(user_id, activation_id, cancel_requested=True)

        ok = await otp_api.cancel_number(activation_id)
        if ok:
            if order:
                await storage.update_order(user_id, activation_id, is_cancelled=True)
            try:
                await query.edit_message_text(
                    "✅ *Number cancelled successfully.*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=main_menu_keyboard(),
                )
            except BadRequest:
                pass
        else:
            try:
                await query.edit_message_text(
                    "⚠️ Could not cancel (already closed or invalid).",
                    reply_markup=main_menu_keyboard(),
                )
            except BadRequest:
                pass

    # ── Noop (placeholder button) ─────────────────────────────────────────────
    elif data == "noop":
        pass

    # ── Navigation ────────────────────────────────────────────────────────────
    elif data == "back:countries":
        await show_countries(query, ctx)

    elif data == "back:main":
        ctx.user_data[_K_AWAITING_SEARCH] = False
        await query.edit_message_text(
            "👋 *Welcome to OTPCart!*\n\nChoose an option below.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )


# ══════════════════════════════════════════════════════════════════════════════
# Navigation helpers
# ══════════════════════════════════════════════════════════════════════════════

async def show_countries(query, ctx) -> None:
    try:
        countries = await otp_api.get_countries()
        await query.edit_message_text(
            "🌍 *Select a country:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=countries_keyboard(countries),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Failed to load countries: {e}")


async def show_services(query, ctx, country_code: str, page: int = 0) -> None:
    try:
        if ctx.user_data.get(_K_COUNTRY) != country_code or _K_SERVICES not in ctx.user_data:
            services = await otp_api.get_services(country_code)
            ctx.user_data[_K_SERVICES] = services
            ctx.user_data[_K_COUNTRY]  = country_code
        else:
            services = ctx.user_data[_K_SERVICES]

        if not services:
            await query.edit_message_text(
                "⚠️ No services available for this country.",
                reply_markup=countries_keyboard(await otp_api.get_countries()),
            )
            return

        await query.edit_message_text(
            "📱 *Select a service:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=services_keyboard(services, page=page),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Failed to load services: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Service flow dispatcher
# ══════════════════════════════════════════════════════════════════════════════

async def handle_service(query, ctx) -> None:
    service_id   = ctx.user_data["service_id"]
    service_name = ctx.user_data["service_name"]
    chat_id      = query.message.chat_id
    user_id      = query.from_user.id

    # Best-effort price lookup from cached services list
    price = "?"
    services = ctx.user_data.get(_K_SERVICES, {})
    if service_id in services:
        price = str(services[service_id].get("service_price", "?"))

    await query.edit_message_text(
        f"📲 Purchasing number for *{service_name.title()}*…",
        parse_mode=ParseMode.MARKDOWN,
    )
    asyncio.create_task(
        _otp_flow(ctx.bot, service_id, service_name, price, chat_id, user_id)
    )


# ══════════════════════════════════════════════════════════════════════════════
# OTP flow (handles multi-SMS, auto-cancel, real-time updates)
# ══════════════════════════════════════════════════════════════════════════════

async def _otp_flow(
    bot,
    service_id: str,
    service_name: str,
    price: str,
    chat_id: int,
    user_id: int,
) -> None:
    """
    Unified OTP flow for all services.
    • Purchases number
    • Registers in storage as an ActiveOrder
    • Monitors SMS every 2 s via otp_api.monitor_sms()
    • Streams each new SMS to the user immediately
    • Auto-cancels if no SMS within OTP_TIMEOUT (5 min)
    • Keeps number alive after first SMS for multi-SMS services
    • Shows OTP even if cancel was requested (Feature 7)
    """

    # ── Purchase ──────────────────────────────────────────────────────────────
    try:
        act_id, phone = await otp_api.purchase_number(service_id)
    except ValueError as e:
        await bot.send_message(chat_id, f"❌ Could not get number: {e}")
        return

    # ── Build ActiveOrder and register ────────────────────────────────────────
    order = storage.ActiveOrder(
        activation_id=act_id,
        phone=phone,
        service_id=service_id,
        service_name=service_name,
        price=price,
        chat_id=chat_id,
    )
    await storage.add_active_order(user_id, order)

    # Record in recently used right after successful purchase
    await storage.record_service_used(user_id, service_id, service_name, price)

    # ── Announce number ───────────────────────────────────────────────────────
    status_msg = await bot.send_message(
        chat_id,
        f"✅ *Your number:* `+{phone}`\n"
        f"📦 Service: *{service_name.title()}*\n"
        f"⏳ Waiting for OTP… (auto-cancel in {OTP_TIMEOUT // 60} min if none received)",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=active_order_keyboard(act_id),
    )
    await storage.update_order(user_id, act_id, message_id=status_msg.message_id)

    # ── Monitor loop (multi-SMS, real-time) ───────────────────────────────────
    sms_count = 0
    async for msg in otp_api.monitor_sms(act_id, first_timeout=OTP_TIMEOUT):

        # Check if user already cancelled via button — but still show any late OTP
        order = await storage.get_active_order(user_id, act_id)

        if msg is None:
            # Timed out — no SMS received → auto-cancel
            await otp_api.cancel_number(act_id)
            await storage.update_order(user_id, act_id, is_expired=True)
            await bot.send_message(
                chat_id,
                f"⏰ *No OTP received.*\n"
                f"Number `+{phone}` automatically cancelled after "
                f"{OTP_TIMEOUT // 60} minutes.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
            await storage.remove_active_order(user_id, act_id)
            return

        # New SMS arrived
        sms_count += 1
        order.sms_messages.append(msg)

        # Feature 7: Even if cancel was requested, display the OTP
        sms_block = _format_sms_block(order.sms_messages)

        if order and order.cancel_requested and sms_count == 1:
            # Cancel was in progress but OTP landed first
            note = "⚠️ _Cancellation was requested but OTP arrived before it completed:_\n\n"
        else:
            note = ""

        await bot.send_message(
            chat_id,
            f"{note}"
            f"📨 *SMS #{sms_count} received!*\n\n"
            f"📱 Number: `+{phone}`\n"
            f"📦 Service: *{service_name.title()}*\n\n"
            f"{sms_block}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=sms_list_keyboard(act_id),
        )

        # If order was cancelled by user before first SMS arrived, stop now
        if order and order.is_cancelled:
            await storage.remove_active_order(user_id, act_id)
            return

    # Loop exited normally (multi-SMS timeout / number expired)
    if sms_count > 0:
        await bot.send_message(
            chat_id,
            f"✅ *Session complete.*\n"
            f"📱 `+{phone}` received *{sms_count} message(s)* in total.\n"
            f"The number is now expired/closed.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
    else:
        await bot.send_message(
            chat_id,
            f"⏰ Number `+{phone}` expired with no messages.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )

    await storage.remove_active_order(user_id, act_id)


# ══════════════════════════════════════════════════════════════════════════════
# Formatting helpers
# ══════════════════════════════════════════════════════════════════════════════

def _format_sms_block(messages: list) -> str:
    if not messages:
        return "_No messages yet._"
    lines = []
    for m in messages:
        lines.append(f"*#{m.index}* — `{m.text}`")
    return "\n".join(lines)


def _format_order_status(order: storage.ActiveOrder) -> str:
    status = "🟢 Active"
    if order.is_cancelled:
        status = "🔴 Cancelled"
    elif order.is_expired:
        status = "🟡 Expired"
    elif order.cancel_requested:
        status = "🟠 Cancel Requested"

    sms_block = _format_sms_block(order.sms_messages)
    return (
        f"📋 *Order Status*\n\n"
        f"📱 Number: `+{order.phone}`\n"
        f"📦 Service: *{order.service_name.title()}*\n"
        f"📊 Status: {status}\n\n"
        f"📨 *Received Messages:*\n{sms_block}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Error handler
# ══════════════════════════════════════════════════════════════════════════════

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update %s:", update, exc_info=ctx.error)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    # Text handler for search queries (only when awaiting_search flag is set)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)

    logger.info("OTPCart Bot is running…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
