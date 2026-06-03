"""
CaseHub - Stripe Payment Service
Handle payment processing via Stripe.
"""
import logging
from typing import Optional
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False


class StripeService:
    """Service for Stripe payment processing."""

    def __init__(self):
        self.api_key = settings.STRIPE_SECRET_KEY
        self.publishable_key = settings.STRIPE_PUBLISHABLE_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        self.success_url = f"{settings.BASE_URL}{settings.PREFIX}/payments/success"
        self.cancel_url = f"{settings.BASE_URL}{settings.PREFIX}/payments/cancel"

        if STRIPE_AVAILABLE and self.api_key:
            stripe.api_key = self.api_key

    def is_configured(self) -> bool:
        """Check if Stripe is properly configured."""
        return STRIPE_AVAILABLE and bool(self.api_key)

    def create_checkout_session(
        self,
        amount: float,
        currency: str = "usd",
        invoice_number: str = None,
        client_email: str = None,
        description: str = None,
        metadata: dict = None
    ) -> dict:
        """Create a Stripe Checkout session for payment.

        Args:
            amount: Payment amount in dollars
            currency: Currency code (default: usd)
            invoice_number: Invoice number for reference
            client_email: Pre-fill customer email
            description: Payment description
            metadata: Additional metadata to store

        Returns:
            Dictionary with session_id and checkout_url
        """
        if not self.is_configured():
            return {"error": "Stripe is not configured"}

        try:
            amount_cents = int(amount * 100)

            session_params = {
                "payment_method_types": ["card"],
                "line_items": [{
                    "price_data": {
                        "currency": currency,
                        "product_data": {
                            "name": f"Invoice {invoice_number}" if invoice_number else "Payment",
                            "description": description or f"Payment for immigration services"
                        },
                        "unit_amount": amount_cents
                    },
                    "quantity": 1
                }],
                "mode": "payment",
                "success_url": f"{self.success_url}?session_id={{CHECKOUT_SESSION_ID}}&invoice={invoice_number}",
                "cancel_url": f"{self.cancel_url}?invoice={invoice_number}",
                "metadata": {
                    "invoice_number": invoice_number or "",
                    "source": "casehub",
                    **(metadata or {})
                }
            }

            if client_email:
                session_params["customer_email"] = client_email

            session = stripe.checkout.Session.create(**session_params)

            return {
                "session_id": session.id,
                "checkout_url": session.url,
                "publishable_key": self.publishable_key
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            return {"error": "Payment processing failed. Please try again."}
        except Exception as e:
            logger.error(f"Unexpected payment error: {str(e)}")
            return {"error": "An unexpected error occurred."}

    def create_payment_intent(
        self,
        amount: float,
        currency: str = "usd",
        invoice_number: str = None,
        client_email: str = None,
        metadata: dict = None
    ) -> dict:
        """Create a Payment Intent for custom payment forms.

        Args:
            amount: Payment amount in dollars
            currency: Currency code
            invoice_number: Invoice reference
            client_email: Customer email
            metadata: Additional metadata

        Returns:
            Dictionary with client_secret for frontend
        """
        if not self.is_configured():
            return {"error": "Stripe is not configured"}

        try:
            amount_cents = int(amount * 100)

            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                metadata={
                    "invoice_number": invoice_number or "",
                    "source": "casehub",
                    **(metadata or {})
                },
                receipt_email=client_email if client_email else None
            )

            return {
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "publishable_key": self.publishable_key
            }

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            return {"error": "Payment processing failed. Please try again."}
        except Exception as e:
            logger.error(f"Unexpected payment error: {str(e)}")
            return {"error": "An unexpected error occurred."}

    def retrieve_session(self, session_id: str) -> dict:
        """Retrieve a checkout session by ID.

        Args:
            session_id: Stripe session ID

        Returns:
            Session data or error
        """
        if not self.is_configured():
            return {"error": "Stripe is not configured"}

        try:
            session = stripe.checkout.Session.retrieve(session_id)
            return {
                "id": session.id,
                "payment_status": session.payment_status,
                "customer_email": session.customer_details.email if session.customer_details else None,
                "amount_total": session.amount_total / 100 if session.amount_total else 0,
                "currency": session.currency,
                "metadata": session.metadata,
                "status": session.status
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            return {"error": "Payment processing failed. Please try again."}

    def retrieve_payment_intent(self, payment_intent_id: str) -> dict:
        """Retrieve a payment intent by ID.

        Args:
            payment_intent_id: Stripe payment intent ID

        Returns:
            Payment intent data or error
        """
        if not self.is_configured():
            return {"error": "Stripe is not configured"}

        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            return {
                "id": intent.id,
                "status": intent.status,
                "amount": intent.amount / 100,
                "currency": intent.currency,
                "metadata": intent.metadata,
                "receipt_email": intent.receipt_email
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            return {"error": "Payment processing failed. Please try again."}

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        """Verify and parse a Stripe webhook event.

        Args:
            payload: Raw request body
            signature: Stripe-Signature header

        Returns:
            Parsed event or error
        """
        if not self.is_configured():
            return {"error": "Stripe is not configured"}

        if not self.webhook_secret:
            return {"error": "Webhook secret not configured"}

        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
            return {
                "type": event.type,
                "data": event.data.object,
                "id": event.id
            }
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Stripe signature verification error: {str(e)}")
            return {"error": "Payment processing failed. Please try again."}
        except Exception as e:
            logger.error(f"Unexpected webhook error: {str(e)}")
            return {"error": "An unexpected error occurred."}

    def create_customer(self, email: str, name: str = None, metadata: dict = None) -> dict:
        """Create a Stripe customer.

        Args:
            email: Customer email
            name: Customer name
            metadata: Additional metadata

        Returns:
            Customer data or error
        """
        if not self.is_configured():
            return {"error": "Stripe is not configured"}

        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata=metadata or {}
            )
            return {
                "id": customer.id,
                "email": customer.email,
                "name": customer.name
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            return {"error": "Payment processing failed. Please try again."}

    def get_payment_methods(self, customer_id: str) -> list:
        """Get saved payment methods for a customer.

        Args:
            customer_id: Stripe customer ID

        Returns:
            List of payment methods
        """
        if not self.is_configured():
            return []

        try:
            methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type="card"
            )
            return [
                {
                    "id": pm.id,
                    "brand": pm.card.brand,
                    "last4": pm.card.last4,
                    "exp_month": pm.card.exp_month,
                    "exp_year": pm.card.exp_year
                }
                for pm in methods.data
            ]
        except stripe.error.StripeError:
            return []


# Singleton instance
stripe_service = StripeService()
