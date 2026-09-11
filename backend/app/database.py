from datetime import datetime, timezone
from sqlalchemy import create_engine, event, String, DateTime, ForeignKey, JSON, Boolean, Float, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from .config import DATABASE_URL

def now():
    return datetime.now(timezone.utc)

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Record:
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Role(Record, Base):
    __tablename__ = 'roles'
    name: Mapped[str] = mapped_column(String(80), unique=True)

class State(Record, Base):
    __tablename__ = 'states'
    name: Mapped[str] = mapped_column(String(100))

class District(Record, Base):
    __tablename__ = 'districts'
    name: Mapped[str] = mapped_column(String(100))
    state_id: Mapped[str] = mapped_column(ForeignKey('states.id'))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)

class User(Record, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(150), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(ForeignKey('roles.id'))
    name: Mapped[str] = mapped_column(String(100))
    district_id: Mapped[str | None] = mapped_column(ForeignKey('districts.id'), nullable=True)
    state_id: Mapped[str | None] = mapped_column(ForeignKey('states.id'), nullable=True)

class Victim(Record, Base):
    __tablename__ = 'victims'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), unique=True)
    alias: Mapped[str] = mapped_column(String(100))

class Case(Record, Base):
    __tablename__ = 'cases'
    victim_id: Mapped[str] = mapped_column(ForeignKey('victims.id'), unique=True)
    district_id: Mapped[str] = mapped_column(ForeignKey('districts.id'))
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    stage: Mapped[str] = mapped_column(String(100), default='Investigation')
    case_type: Mapped[str] = mapped_column(String(100), default='Complainant')
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)

class Consent(Record, Base):
    __tablename__ = 'consents'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    wellbeing: Mapped[bool] = mapped_column(Boolean)
    voice: Mapped[bool] = mapped_column(Boolean)
    language: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(20), default='1.0')

class CaseRecord(Record):
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

class CaseEvent(CaseRecord, Base):
    __tablename__ = 'case_events'

class Assessment(CaseRecord, Base):
    __tablename__ = 'assessments'

class AssessmentRecord(Record):
    assessment_id: Mapped[str] = mapped_column(ForeignKey('assessments.id'), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

class AssessmentResponse(AssessmentRecord, Base):
    __tablename__ = 'assessment_responses'
class NLPResult(AssessmentRecord, Base):
    __tablename__ = 'nlp_results'
class BehaviourFeature(AssessmentRecord, Base):
    __tablename__ = 'behaviour_features'
class RiskScore(AssessmentRecord, Base):
    __tablename__ = 'risk_scores'
class RiskExplanation(AssessmentRecord, Base):
    __tablename__ = 'risk_explanations'
class VoiceSession(CaseRecord, Base):
    __tablename__ = 'voice_sessions'
class VoiceFeature(Record, Base):
    __tablename__ = 'voice_features'
    voice_session_id: Mapped[str] = mapped_column(ForeignKey('voice_sessions.id'))
    data: Mapped[dict] = mapped_column(JSON)

class Alert(CaseRecord, Base):
    __tablename__ = 'alerts'
    status: Mapped[str] = mapped_column(String(40), default='New')
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)

class Intervention(CaseRecord, Base):
    __tablename__ = 'interventions'
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    assigned_to: Mapped[str] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(40), default='Assigned')

class FollowUp(CaseRecord, Base):
    __tablename__ = 'follow_ups'
    assigned_to: Mapped[str] = mapped_column(ForeignKey('users.id'))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default='Scheduled')

class SupportRequest(CaseRecord, Base):
    __tablename__ = 'support_requests'
    status: Mapped[str] = mapped_column(String(40), default='New')

class Notification(Record, Base):
    __tablename__ = 'notifications'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    read: Mapped[bool] = mapped_column(Boolean, default=False)

class AuditLog(Record, Base):
    __tablename__ = 'audit_logs'
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str] = mapped_column(String(150))

class ModelVersion(Record, Base):
    __tablename__ = 'model_versions'
    data: Mapped[dict] = mapped_column(JSON)

class RevokedToken(Base):
    __tablename__ = 'revoked_tokens'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # JWT jti
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

def get_db():
    with SessionLocal() as session:
        yield session
