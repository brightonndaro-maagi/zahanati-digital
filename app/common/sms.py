import logging

from flask import current_app

log = logging.getLogger(__name__)


class SMSError(Exception):
    pass


class MemoryGateway:
    """Tests only: keeps messages in app.extensions['sms_outbox']."""
    def send(self, phone, message):
        current_app.extensions.setdefault("sms_outbox", []).append((phone, message))


class ConsoleGateway:
    """Development only: prints the message in the server log. Never use in production."""
    def send(self, phone, message):
        log.warning("[DEV SMS to %s] %s", phone, message)


class BeemGateway:
    """Beem Africa SMS API. Credentials come from BEEM_API_KEY / BEEM_SECRET_KEY / BEEM_SOURCE_ADDR."""
    URL = "https://apisms.beem.africa/v1/send"

    def send(self, phone, message):
        import requests
        cfg = current_app.config
        if not (cfg.get("BEEM_API_KEY") and cfg.get("BEEM_SECRET_KEY") and cfg.get("BEEM_SOURCE_ADDR")):
            raise SMSError("Beem credentials are not configured")
        payload = {
            "source_addr": cfg["BEEM_SOURCE_ADDR"], "schedule_time": "", "encoding": 0, "message": message,
            "recipients": [{"recipient_id": 1, "dest_addr": phone.lstrip("+")}],
        }
        try:
            r = requests.post(self.URL, json=payload, auth=(cfg["BEEM_API_KEY"], cfg["BEEM_SECRET_KEY"]), timeout=10)
        except requests.RequestException as e:
            raise SMSError(f"Beem request failed: {e}")
        if r.status_code != 200:
            raise SMSError(f"Beem returned HTTP {r.status_code}")
        try:
            body = r.json()
        except ValueError:
            body = {}
        if body.get("successful") is False:
            raise SMSError(f"Beem rejected the message: {body.get('message')}")


_GATEWAYS = {"memory": MemoryGateway, "console": ConsoleGateway, "beem": BeemGateway}


def get_gateway():
    name = current_app.config["SMS_PROVIDER"]
    if name not in _GATEWAYS:
        raise SMSError(f"Unknown SMS provider '{name}'")
    return _GATEWAYS[name]()
