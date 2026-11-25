import os
from datetime import datetime, timezone

import click
from flask import Flask

from config import CONFIG_MAP
from app.common.errors import register_error_handlers
from app.extensions import cors, db, jwt, limiter, migrate


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(CONFIG_MAP[config_name])

    if not app.config["TESTING"]:
        for key in ("SECRET_KEY", "JWT_SECRET_KEY", "SQLALCHEMY_DATABASE_URI"):
            if not app.config.get(key):
                raise RuntimeError(f"Missing required configuration: {key} (set it in .env)")
        if not app.config["FILE_ENCRYPTION_KEYS"]:
            if app.config["DEBUG"]:
                app.logger.warning("FILE_ENCRYPTION_KEYS is not set: prescription uploads are disabled. Run: flask generate-fernet-key")
            else:
                raise RuntimeError("FILE_ENCRYPTION_KEYS is required (run: flask generate-fernet-key)")
        if not app.config["PAYMENT_CALLBACK_SECRET"] or len(app.config["PAYMENT_CALLBACK_SECRET"]) < 24:
            if app.config["DEBUG"]:
                app.logger.warning("PAYMENT_CALLBACK_SECRET is missing/short: payment callbacks will be rejected")
            else:
                raise RuntimeError("PAYMENT_CALLBACK_SECRET (24+ random characters) is required")
        if not app.config["DEBUG"] and app.config["PAYMENT_PROVIDER"] == "simulator" and not app.config["ALLOW_PAYMENT_SIMULATOR"]:
            raise RuntimeError("PAYMENT_PROVIDER 'simulator' is not a real payment provider. Add a provider adapter "
                               "(app/payments/providers.py) or set ALLOW_PAYMENT_SIMULATOR=true for a demo.")
        if not app.config["DEBUG"] and app.config["SMS_PROVIDER"] != "beem":
            raise RuntimeError("SMS_PROVIDER must be 'beem' outside development (OTP codes must never be logged)")

    from app.common.validators import UUIDConverter
    app.url_map.converters["uid"] = UUIDConverter

    if app.config["PROXY_HOPS"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        n = app.config["PROXY_HOPS"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from app import models  # noqa: F401  (register models for migrations)
    _register_jwt_callbacks()
    register_error_handlers(app)
    _register_blueprints(app)
    _register_cli(app)
    _register_hooks(app)
    _register_swagger(app)

    @app.get("/api/v1/health")
    def health():
        """Health check for load balancers and uptime monitors.
        ---
        tags: [Auth]
        responses:
          200: {description: The API is running}
        """
        return {"success": True, "message": "Zahanati Digital API is running"}

    return app


def _register_swagger(app):
    """OpenAPI 2.0 spec at /api/openapi.json and Swagger UI at /api/docs/ (set SWAGGER_ENABLED=false to hide them)."""
    if not app.config["SWAGGER_ENABLED"]:
        return
    from flasgger import Swagger
    from app.docs import enrich

    class EnrichedSwagger(Swagger):
        def get_apispecs(self, endpoint="apispec"):
            return enrich(super().get_apispecs(endpoint), app)
    template = {
        "swagger": "2.0",
        "info": {"title": "Zahanati Digital API", "version": "1.0.0",
                 "description": ("REST API of the Zahanati Digital health platform (patients, doctors, pharmacies, admins).\n\n"
                                 "**Authentication:** log in (`/auth/otp/verify` for patients, `/auth/login` for doctors, pharmacies and admins), "
                                 "then send `Authorization: Bearer <access_token>`. Use **Authorize** below to try endpoints.\n\n"
                                 "**Language:** send `Accept-Language: sw` or `en` (or `?lang=`). **Responses:** `{success, message, data, meta?}`; "
                                 "errors are `{success:false, message, errors?, request_id}`. Chat is not an emergency service: call 112.")},
        "basePath": "/",
        "securityDefinitions": {"Bearer": {"type": "apiKey", "name": "Authorization", "in": "header",
                                           "description": "Type: Bearer <access_token>"}},
        "tags": [{"name": t} for t in ("Auth", "Patients", "Doctors", "Availability", "Specialisations", "Appointments", "Pharmacies",
                                       "Medicines", "Pharmacy catalogue", "Orders", "Payments", "Prescriptions", "Consultations",
                                       "Notifications", "Content", "HEDHI", "Admin", "Admin content")],
    }
    config = {"headers": [], "specs": [{"endpoint": "apispec", "route": "/api/openapi.json",
                                        "rule_filter": lambda rule: rule.rule.startswith("/api/v1"), "model_filter": lambda tag: True}],
              "static_url_path": "/flasgger_static", "swagger_ui": True, "specs_route": "/api/docs/"}
    EnrichedSwagger(app, template=template, config=config)


def _register_hooks(app):
    import re
    import uuid
    from flask import g, request

    @app.before_request
    def _request_id():
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if re.fullmatch(r"[A-Za-z0-9._-]{8,64}", incoming) else uuid.uuid4().hex

    @app.after_request
    def _security_headers(resp):
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        if request.path.startswith("/api/") and not request.path.startswith("/api/docs"):
            resp.headers.setdefault("Cache-Control", "no-store")
            resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if request.is_secure and not app.config["DEBUG"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp


def _register_blueprints(app):
    from app.auth.routes import bp as auth_bp
    from app.patients.routes import bp as patients_bp
    from app.doctors.routes import bp as doctors_bp, spec_bp
    from app.admin.routes import bp as admin_bp
    from app.appointments.routes import bp as appointments_bp, availability_bp
    from app.pharmacies.routes import bp as pharmacies_bp
    from app.medicines.routes import bp as medicines_bp, catalogue_bp
    from app.orders.routes import bp as orders_bp
    from app.payments.routes import bp as payments_bp
    from app.consultations.routes import bp as consultations_bp
    from app.prescriptions.routes import bp as prescriptions_bp
    from app.doctors.extras import bp as doctor_extras_bp
    from app.content.routes import public_bp as content_public_bp, admin_bp as content_admin_bp
    from app.hedhi.routes import bp as hedhi_bp
    from app.admin.management import bp as admin_management_bp
    from app.notifications.routes import bp as notifications_bp
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    if app.config["FEATURE_APPOINTMENTS"]:
        app.register_blueprint(availability_bp, url_prefix="/api/v1/doctors")
        app.register_blueprint(appointments_bp, url_prefix="/api/v1/appointments")
    app.register_blueprint(patients_bp, url_prefix="/api/v1/patients")
    app.register_blueprint(doctors_bp, url_prefix="/api/v1/doctors")
    app.register_blueprint(spec_bp, url_prefix="/api/v1/specialisations")
    app.register_blueprint(pharmacies_bp, url_prefix="/api/v1/pharmacies")
    app.register_blueprint(catalogue_bp, url_prefix="/api/v1/pharmacies")
    app.register_blueprint(medicines_bp, url_prefix="/api/v1/medicines")
    app.register_blueprint(orders_bp, url_prefix="/api/v1/orders")
    app.register_blueprint(payments_bp, url_prefix="/api/v1")
    app.register_blueprint(consultations_bp, url_prefix="/api/v1/consultations")
    app.register_blueprint(prescriptions_bp, url_prefix="/api/v1")
    app.register_blueprint(doctor_extras_bp, url_prefix="/api/v1/doctors")
    app.register_blueprint(notifications_bp, url_prefix="/api/v1/notifications")
    app.register_blueprint(admin_bp, url_prefix="/api/v1/admin")
    app.register_blueprint(content_admin_bp, url_prefix="/api/v1/admin")
    app.register_blueprint(admin_management_bp, url_prefix="/api/v1/admin")
    app.register_blueprint(content_public_bp, url_prefix="/api/v1")
    app.register_blueprint(hedhi_bp, url_prefix="/api/v1/hedhi")


def _register_jwt_callbacks():
    from app.common.errors import error_response
    from app.models.user import TokenBlocklist

    @jwt.token_in_blocklist_loader
    def _blocked(_header, payload):
        return db.session.query(TokenBlocklist.id).filter_by(jti=payload["jti"]).first() is not None

    @jwt.unauthorized_loader
    def _missing(msg):
        return error_response("Authentication required", 401)

    @jwt.invalid_token_loader
    def _invalid(msg):
        return error_response("Invalid token", 401)

    @jwt.expired_token_loader
    def _expired(_h, _p):
        return error_response("Token has expired", 401)

    @jwt.revoked_token_loader
    def _revoked(_h, _p):
        return error_response("Token has been revoked", 401)


def _register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--phone", prompt=True, help="e.g. 0712345678")
    @click.option("--email", default="", help="optional")
    @click.password_option()
    def create_admin(phone, email, password):
        """Create an administrator account."""
        from app.common.phone import normalize_phone
        from app.models.user import User
        normalized = normalize_phone(phone)
        if not normalized:
            raise click.ClickException("Invalid Tanzanian mobile number")
        from marshmallow import ValidationError
        from app.common.passwords import check_password
        try:
            check_password(password)
        except ValidationError as e:
            raise click.ClickException(e.messages[0])
        if User.query.filter_by(phone=normalized).first() or (email and User.query.filter_by(email=email.lower()).first()):
            raise click.ClickException("A user with that phone or email already exists")
        u = User(phone=normalized, email=email.lower() or None, role="admin")
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo("Administrator created.")

    @app.cli.command("seed-specialisations")
    def seed_specialisations():
        """Insert common specialisations."""
        from app.models.doctor import Specialisation
        names = ["General Practitioner", "Paediatrics", "Gynaecology & Obstetrics", "Internal Medicine",
                 "Surgery", "Dermatology", "Cardiology", "Ophthalmology", "ENT", "Psychiatry", "Dentistry"]
        for n in names:
            if not Specialisation.query.filter_by(name=n).first():
                db.session.add(Specialisation(name=n))
        db.session.commit()
        click.echo("Specialisations seeded.")

    @app.cli.command("generate-fernet-key")
    def generate_fernet_key():
        """Print a new key for FILE_ENCRYPTION_KEYS."""
        from cryptography.fernet import Fernet
        click.echo(Fernet.generate_key().decode())

    @app.cli.command("expire-orders")
    def expire_orders_cmd():
        """Expire unpaid orders older than 24 h. Run every few minutes from cron."""
        from app.orders.services import expire_due
        click.echo(f"Expired {expire_due(limit=10000)} order(s).")

    @app.cli.command("purge-prescriptions")
    def purge_prescriptions_cmd():
        """Delete prescription files older than the retention period (2 years). Run daily from cron."""
        from app.orders.services import purge_expired_prescriptions
        click.echo(f"Purged {purge_expired_prescriptions()} prescription file(s).")

    @app.cli.command("expire-payments")
    def expire_payments_cmd():
        """Fail payments with no provider confirmation after PAYMENT_TIMEOUT_MINUTES and release their stock."""
        from app.payments.services import expire_pending
        click.echo(f"Failed {expire_pending()} stuck payment(s).")

    @app.cli.command("purge-inactive-hedhi")
    def purge_inactive_hedhi_cmd():
        """Delete HEDHI data of customers who have not logged in for 2 years. Run daily from cron."""
        from app.hedhi.services import purge_inactive
        users, entries = purge_inactive()
        click.echo(f"Purged {entries} HEDHI entr(y/ies) of {users} inactive user(s).")
