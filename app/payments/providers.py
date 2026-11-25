"""Payment provider adapters. A real aggregator adapter (M-Pesa / Tigo Pesa / Airtel Money) must implement
`initiate`; the rest of the payment flow (stock reservation, protected callback, idempotency, refunds)
is provider-independent. Only the simulator exists until a provider is chosen."""
import uuid

from flask import current_app


class PaymentProviderError(Exception):
    pass


class SimulatorProvider:
    """Development/test provider: the 'customer' confirms by sending a signed callback yourself."""
    name = "simulator"

    def initiate(self, payment):
        return f"SIM-{uuid.uuid4().hex[:16]}"


_PROVIDERS = {"simulator": SimulatorProvider}


def get_provider():
    name = current_app.config["PAYMENT_PROVIDER"]
    if name not in _PROVIDERS:
        raise PaymentProviderError(f"Unknown payment provider '{name}'")
    return _PROVIDERS[name]()
