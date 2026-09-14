"""
Email alerts — ported from the uploaded email_alerts.py.

Only change from the original: EMAIL_CONFIG and the cooldown window now
come from Django settings (which load from .env) instead of being
hardcoded in this file. The Gmail app password Jj had in the original
should be rotated since it was committed in plaintext — put the new one
in .env, never in source.
"""
import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings

VAR_DIR = settings.BASE_DIR / "var"
VAR_DIR.mkdir(exist_ok=True)
SIGNAL_CACHE_FILE = VAR_DIR / "last_signal.json"


def load_last_signal():
    try:
        if SIGNAL_CACHE_FILE.exists():
            with open(SIGNAL_CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Error loading last signal: {e}")
    return None


def save_last_signal(signal_data):
    try:
        signal_data["timestamp"] = datetime.now().timestamp()
        with open(SIGNAL_CACHE_FILE, "w") as f:
            json.dump(signal_data, f)
    except Exception as e:
        logging.error(f"Error saving signal: {e}")


def should_send_alert(signal, price_data):
    last_signal = load_last_signal()
    if not last_signal:
        return True

    current_time = datetime.now().timestamp()
    time_diff_minutes = (current_time - last_signal.get("timestamp", 0)) / 60

    if signal["direction"] != last_signal.get("signal", {}).get("direction"):
        logging.info("Signal direction changed - sending alert")
        return True

    if time_diff_minutes < settings.ALERT_COOLDOWN_MINUTES:
        last_entry = last_signal.get("price_data", {}).get("entry", 0)
        price_change_percent = abs((price_data["entry"] - last_entry) / last_entry) * 100 if last_entry else 0

        if price_change_percent > 2:
            logging.info(f"Significant price change ({price_change_percent:.1f}%) - sending alert")
            return True

        if signal.get("pattern") != last_signal.get("signal", {}).get("pattern"):
            logging.info("Pattern changed - sending alert")
            return True

        logging.info(
            f"Skipping alert - cooldown period ({time_diff_minutes:.0f} min < {settings.ALERT_COOLDOWN_MINUTES} min)"
        )
        return False

    logging.info("Cooldown period expired - sending new alert")
    return True


def format_trade_alert(signal, price_data, advice, user_email=None):
    market_name = price_data.get("market_name", signal.get("market_name", signal.get("symbol", "Unknown Market")))
    symbol = signal.get("symbol", "")
    direction = signal.get("direction", "Buy")
    dir_color = "#10b981" if direction == "Buy" else "#ef4444"
    rr = signal.get("risk_reward")
    rr_line = f"1:{rr:.1f}" if rr else "n/a"
    quality = signal.get("setup_quality", 0)
    strength = signal.get("signal_strength", 0)
    timeframe = signal.get("timeframe", "1H")
    entry_type = signal.get("entry_type", "Algorithmic Setup")
    entry_p = price_data.get("entry", signal.get("price", 0))
    sl_p = price_data.get("stop_loss", signal.get("stop_loss", 0))
    tp_p = price_data.get("take_profit", signal.get("take_profit", 0))

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px; color: #1e293b; }}
            .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
            .header {{ background: linear-gradient(135deg, #ff6a00 0%, #ff8c00 100%); padding: 24px; text-align: center; color: #ffffff; }}
            .logo-title {{ font-size: 20px; font-weight: 800; letter-spacing: 1px; margin: 0; display: inline-block; }}
            .badge-dir {{ display: inline-block; padding: 6px 16px; border-radius: 9999px; background: {dir_color}; color: #ffffff; font-weight: 700; font-size: 16px; margin-top: 12px; }}
            .content {{ padding: 24px; }}
            .market-banner {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin-bottom: 20px; text-align: center; }}
            .market-title {{ font-size: 18px; font-weight: 700; color: #0f172a; margin: 0 0 4px; }}
            .market-sub {{ font-size: 13px; color: #64748b; margin: 0; }}
            .grid {{ display: table; width: 100%; margin-bottom: 20px; }}
            .row {{ display: table-row; }}
            .col {{ display: table-cell; width: 50%; padding: 10px; vertical-align: top; }}
            .card {{ background: #f8fafc; border-radius: 10px; padding: 12px 14px; border: 1px solid #edf2f7; }}
            .card-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; font-weight: 600; margin-bottom: 4px; }}
            .card-val {{ font-size: 16px; font-weight: 700; color: #0f172a; font-family: monospace; }}
            .advisory {{ background: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 0 8px 8px 0; padding: 14px 16px; margin: 20px 0; font-size: 13px; color: #92400e; line-height: 1.5; }}
            .footer {{ border-top: 1px solid #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; background: #fafafa; }}
            .footer a {{ color: #ff6a00; text-decoration: none; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo-title">MONEYBOTS ALERTS</div>
                <div><span class="badge-dir">{direction.upper()} SIGNAL</span></div>
            </div>
            <div class="content">
                <div class="market-banner">
                    <div class="market-title">{market_name} ({symbol})</div>
                    <div class="market-sub">Timeframe: <strong>{timeframe}</strong> &bull; Setup: <strong>{entry_type}</strong></div>
                </div>

                <div class="grid">
                    <div class="row">
                        <div class="col">
                            <div class="card">
                                <div class="card-label">Entry Price</div>
                                <div class="card-val">{entry_p:.5f}</div>
                            </div>
                        </div>
                        <div class="col">
                            <div class="card">
                                <div class="card-label">Setup Quality</div>
                                <div class="card-val" style="color: #ff6a00;">{quality:.1f}%</div>
                            </div>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col">
                            <div class="card">
                                <div class="card-label">Stop Loss</div>
                                <div class="card-val" style="color: #ef4444;">{sl_p:.5f}</div>
                            </div>
                        </div>
                        <div class="col">
                            <div class="card">
                                <div class="card-label">Take Profit</div>
                                <div class="card-val" style="color: #10b981;">{tp_p:.5f}</div>
                            </div>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col">
                            <div class="card">
                                <div class="card-label">Risk/Reward</div>
                                <div class="card-val">{rr_line}</div>
                            </div>
                        </div>
                        <div class="col">
                            <div class="card">
                                <div class="card-label">Signal Strength</div>
                                <div class="card-val">{strength:.2f}</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="advisory">
                    <strong>Analysis Note:</strong> {advice}
                </div>
            </div>
            <div class="footer">
                <p style="margin: 0 0 6px;">You received this alert because you personalized your notification preferences on Moneybots.</p>
                <p style="margin: 0;">Automated analysis only &bull; Never risk more than you can afford to lose.</p>
            </div>
        </div>
    </body>
    </html>
    """


def send_single_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email to a single recipient using Django EMAIL_CONFIG."""
    cfg = settings.EMAIL_CONFIG
    if not cfg["HOST_USER"] or not cfg["HOST_PASSWORD"]:
        logging.info("Email skipped: EMAIL_HOST_USER or EMAIL_HOST_PASSWORD not configured.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Moneybots Alerts <{cfg['HOST_USER']}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(cfg["HOST"], cfg["PORT"], timeout=10)
        if cfg.get("USE_TLS", True):
            server.starttls()
        server.login(cfg["HOST_USER"], cfg["HOST_PASSWORD"])
        server.send_message(msg)
        server.quit()
        logging.info(f"Alert email delivered to {to_email}")
        return True
    except Exception as e:
        logging.error(f"Failed sending alert email to {to_email}: {e}")
        return False


def get_alert_recipients(signal):
    """Find all user emails whose personalized preferences match this signal."""
    recipients = set()
    cfg = settings.EMAIL_CONFIG
    
    # 1. Check UserProfiles in DB
    try:
        from analysis.models import UserProfile
        profiles = UserProfile.objects.filter(
            email_alerts_enabled=True,
            user__email__isnull=False
        ).exclude(user__email="").select_related("user")

        sym = signal.get("symbol", "")
        direction = signal.get("direction", "")
        quality = signal.get("setup_quality", 0)
        timeframe = signal.get("timeframe", "1H")

        for prof in profiles:
            # Check favorites only filter
            if prof.alert_favorites_only and (not prof.favorites or sym not in prof.favorites):
                continue
            # Check min quality threshold
            if quality < prof.alert_min_quality:
                continue
            # Check direction filter
            if prof.alert_directions != "all" and prof.alert_directions != direction:
                continue
            # Check timeframe filter
            if prof.alert_timeframe != "all" and prof.alert_timeframe != timeframe:
                continue

            recipients.add(prof.user.email)
    except Exception as e:
        logging.warning(f"Could not load UserProfiles for alert: {e}")

    # 2. Add CONTACT_EMAIL if defined in .env as global administrator/fallback
    if cfg.get("CONTACT_EMAIL"):
        recipients.add(cfg["CONTACT_EMAIL"])

    return list(recipients)


def send_trade_alert(signal, price_data, advice):
    """Dispatches trade alert to all users matching personalized criteria."""
    cfg = settings.EMAIL_CONFIG
    if not cfg["HOST_USER"] or not cfg["HOST_PASSWORD"]:
        logging.info("Email alert skipped: EMAIL_HOST_USER/PASSWORD not set in .env")
        return False

    try:
        if not should_send_alert(signal, price_data):
            return False

        recipients = get_alert_recipients(signal)
        if not recipients:
            logging.info(f"No opted-in users matching signal {signal.get('symbol')} criteria.")
            return False

        market_name = price_data.get("market_name", signal.get("symbol"))
        subject = f"[Moneybots Signal] {signal['direction']} — {market_name} ({signal.get('setup_quality', 0):.0f}% Setup)"
        html_content = format_trade_alert(signal, price_data, advice)

        sent_count = 0
        for email in recipients:
            if send_single_email(email, subject, html_content):
                sent_count += 1

        save_last_signal({"signal": signal, "price_data": price_data, "timestamp": datetime.now().timestamp()})
        logging.info(f"Trade alert sent to {sent_count}/{len(recipients)} recipients for {signal['symbol']}")
        return sent_count > 0

    except Exception as e:
        logging.error(f"Failed in send_trade_alert: {e}")
        return False


def send_test_alert(user) -> tuple[bool, str]:
    """Sends a verification test alert to a specific user's email."""
    if not user or not user.email:
        return False, "No email address found for this user."

    cfg = settings.EMAIL_CONFIG
    if not cfg["HOST_USER"] or not cfg["HOST_PASSWORD"]:
        return False, "Email sending server (SMTP) is not configured in .env."

    mock_signal = {
        "symbol": "frxEURUSD",
        "market_name": "EUR/USD",
        "direction": "Buy",
        "signal_strength": 0.85,
        "setup_quality": 88.0,
        "entry_type": "Institutional Orderflow Confirmation",
        "timeframe": "1H",
        "risk_reward": 2.4,
    }
    mock_price = {
        "entry": 1.08450,
        "stop_loss": 1.08150,
        "take_profit": 1.09170,
        "market_name": "EUR/USD",
    }
    advice = "This is a test notification confirming your personalized Moneybots email alerts are active and functional!"

    subject = "[Moneybots Test Alert] Personalized Signal System Connected"
    html = format_trade_alert(mock_signal, mock_price, advice, user_email=user.email)

    success = send_single_email(user.email, subject, html)
    if success:
        return True, f"Test alert successfully delivered to {user.email}!"
    else:
        return False, f"Could not send email to {user.email}. Check SMTP credentials."

