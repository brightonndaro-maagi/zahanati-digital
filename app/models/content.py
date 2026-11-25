from sqlalchemy.orm import declared_attr

from app.extensions import db
from app.models.base import TimestampMixin, fk, uuid_pk


class ContentMixin(TimestampMixin):
    """Reviewed medical content. The working copy lives in the columns; what the public sees is `live`, a snapshot taken
    when a named reviewer approved it. Editing never changes `live`: the old approved text stays visible until the new
    version is approved (spec 15.1: every change needs a new review)."""
    id = uuid_pk()
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.String(500))
    body = db.Column(db.Text)
    keywords = db.Column(db.String(300))
    language = db.Column(db.String(2), nullable=False, default="sw")
    status = db.Column(db.String(10), nullable=False, default="draft", index=True)  # draft = has changes not yet approved
    edition = db.Column(db.Integer, nullable=False, default=0)
    live = db.Column(db.JSON(none_as_null=True))

    @declared_attr
    def created_by_user_id(cls):
        return fk("users.id", nullable=True)


class FirstAidGuide(ContentMixin, db.Model):
    __tablename__ = "first_aid_guides"
    __table_args__ = (db.CheckConstraint("status IN ('draft','published')", name="ck_first_aid_status"),
                      db.CheckConstraint("language IN ('sw','en')", name="ck_first_aid_language"))
    emergency_warning = db.Column(db.Text, nullable=False)  # when to call an ambulance / 112
    steps_to_do = db.Column(db.JSON, nullable=False)
    steps_to_avoid = db.Column(db.JSON, nullable=False)


class HealthEducation(ContentMixin, db.Model):
    __tablename__ = "health_education"
    __table_args__ = (db.CheckConstraint("status IN ('draft','published')", name="ck_health_edu_status"),
                      db.CheckConstraint("language IN ('sw','en')", name="ck_health_edu_language"),
                      db.CheckConstraint("stage BETWEEN 1 AND 8", name="ck_health_edu_stage"))
    stage = db.Column(db.Integer, nullable=False, index=True)  # position in the reproductive-health journey (1-8)


class HedhiCycle(db.Model):
    """One menstrual cycle entry. `data` is a Fernet token of a JSON document; nothing about the cycle is stored in clear."""
    __tablename__ = "hedhi_cycles"
    id = uuid_pk()
    user_id = fk("users.id", nullable=False, index=True)
    data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)
