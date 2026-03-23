"""
ELX Index Pro — Stripe Billing Integration
Handles checkout sessions, webhook events, and subscription verification.
"""

import os
import stripe
import sqlite3
from datetime import datetime
from pathlib import Path

# Stripe configuration
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "https://elxindex.com")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "elx.db"


def _ensure_pro_table():
    """Create the pro_subscribers table if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pro_subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            status TEXT DEFAULT 'active',
            pro_token TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def create_checkout_session() -> dict:
    """Create a Stripe Checkout session for ELX Index Pro subscription."""
    if not stripe.api_key or not STRIPE_PRICE_ID:
        return {"error": "Stripe not configured"}

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{
                "price": STRIPE_PRICE_ID,
                "quantity": 1,
            }],
            success_url=f"{BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/pricing",
            metadata={"product": "elx_index_pro"},
        )
        return {"url": session.url, "session_id": session.id}
    except Exception as e:
        return {"error": str(e)}


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Process Stripe webhook events."""
    if not STRIPE_WEBHOOK_SECRET:
        # In development, parse without signature verification
        import json
        event = json.loads(payload)
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            return {"error": str(e)}

    event_type = event.get("type", "")

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        _activate_subscription(session)
    elif event_type == "customer.subscription.deleted":
        sub = event["data"]["object"]
        _deactivate_subscription(sub)
    elif event_type == "invoice.payment_failed":
        invoice = event["data"]["object"]
        _handle_payment_failed(invoice)

    return {"received": True, "type": event_type}


def _activate_subscription(session: dict):
    """Activate a pro subscription after successful checkout."""
    _ensure_pro_table()
    import secrets
    token = secrets.token_urlsafe(32)
    email = session.get("customer_email", "") or session.get("customer_details", {}).get("email", "")
    customer_id = session.get("customer", "")
    subscription_id = session.get("subscription", "")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        INSERT INTO pro_subscribers (email, stripe_customer_id, stripe_subscription_id, status, pro_token)
        VALUES (?, ?, ?, 'active', ?)
    """, (email, customer_id, subscription_id, token))
    conn.commit()
    conn.close()
    print(f"[ELX Pro] Activated: {email} (token: {token[:8]}...)")
    return token


def _deactivate_subscription(sub: dict):
    """Deactivate a subscription when canceled."""
    _ensure_pro_table()
    sub_id = sub.get("id", "")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        UPDATE pro_subscribers SET status = 'canceled', updated_at = ? WHERE stripe_subscription_id = ?
    """, (datetime.now().isoformat(), sub_id))
    conn.commit()
    conn.close()
    print(f"[ELX Pro] Deactivated subscription: {sub_id}")


def _handle_payment_failed(invoice: dict):
    """Handle failed payment."""
    sub_id = invoice.get("subscription", "")
    print(f"[ELX Pro] Payment failed for subscription: {sub_id}")


def verify_pro_token(token: str) -> bool:
    """Check if a pro token is valid and active."""
    if not token:
        return False
    _ensure_pro_table()
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute(
        "SELECT status FROM pro_subscribers WHERE pro_token = ? AND status = 'active'",
        (token,)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def verify_session(session_id: str) -> dict:
    """Verify a checkout session and return the pro token."""
    if not stripe.api_key:
        return {"error": "Stripe not configured"}
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            # Find the token for this session's customer
            _ensure_pro_table()
            customer_id = session.customer
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.execute(
                "SELECT pro_token FROM pro_subscribers WHERE stripe_customer_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (customer_id,)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                return {"valid": True, "token": row[0]}
            # If webhook hasn't fired yet, activate manually
            token = _activate_subscription({
                "customer_email": session.customer_details.email if session.customer_details else "",
                "customer": customer_id,
                "subscription": session.subscription,
            })
            return {"valid": True, "token": token}
        return {"valid": False, "reason": "Payment not completed"}
    except Exception as e:
        return {"error": str(e)}


def get_pro_subscribers() -> list:
    """Get all pro subscribers."""
    _ensure_pro_table()
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("SELECT email, status, created_at FROM pro_subscribers ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"email": r[0], "status": r[1], "created_at": r[2]} for r in rows]
