import os

# ── Telegram ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ── OTPDoctor ─────────────────────────────────────────────
OTP_API_KEY  = os.getenv("OTP_API_KEY", "q6v6ef7r50mm4wkbkmq8a1ntxs8qx3wl")
OTP_BASE_URL = "https://www.otpdoctor.in/stubs/handler_api.php"

# ── Timing ────────────────────────────────────────────────
OTP_POLL_INTERVAL  = 2    # seconds between status checks (real-time monitoring)
OTP_TIMEOUT        = 300  # seconds to wait for FIRST OTP before auto-cancel (5 min)
MULTI_SMS_TIMEOUT  = 1200 # seconds to keep number alive after first OTP (20 min)

# ── UX / Limits ───────────────────────────────────────────
RECENTLY_USED_MAX  = 5    # max recently-used entries stored per user
