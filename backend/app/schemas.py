from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Login(Strict):
    email: str = Field(min_length=3,max_length=150)
    password: str = Field(min_length=1,max_length=128)
class Register(Login):
    name: str = Field(min_length=1,max_length=100)
    role: Literal['victim','counsellor','officer','state','national','admin']
    district_id: str | None = None
    state_id: str | None = None

class ConsentInput(Strict):
    wellbeing: bool
    voice: bool = False
    language: Literal['en','hi','hinglish'] = 'en'
class TextInput(Strict):
    text: str = Field(max_length=10000)
    language: Literal['en','hi','hinglish'] = 'en'
class Responses(Strict):
    feeling: int | None = Field(default=None,ge=0,le=4)
    fear: int | None = Field(default=None,ge=0,le=4)
    sleep: int | None = Field(default=None,ge=0,le=4)
    daily: int | None = Field(default=None,ge=0,le=4)
    avoidance: int | None = Field(default=None,ge=0,le=4)
    legal: int | None = Field(default=None,ge=0,le=4)
    threat: bool | None = None
    safe: bool | None = None
    support: bool | None = None
    need: str = Field(default='',max_length=200)
class AssessmentInput(TextInput):
    case_id: str
    responses: Responses
    voice_session_id: str | None = None
    @model_validator(mode='after')
    def nonempty(self):
        if not self.text.strip() and not any(v is not None and v != '' for v in self.responses.model_dump().values()) and not self.voice_session_id:
            raise ValueError('Please answer at least one question or provide text')
        return self

class CaseInput(Strict):
    victim_id: str
    district_id: str
    case_type: Literal['Complainant','Witness'] = 'Complainant'
class EventInput(Strict):
    case_id: str
    title: str = Field(min_length=3,max_length=150)
    notes: str = Field(default='',max_length=3000)
    kind: Literal['general','threat','court_event','compensation_delay','investigation_delay','rehabilitation'] = 'general'
    active: bool = True
class InterventionInput(Strict):
    case_id: str
    kind: str = Field(min_length=3,max_length=150)
    assigned_to: str
    notes: str = Field(default='',max_length=3000)
class InterventionUpdate(Strict):
    status: Literal['Assigned','In Progress','Completed','Cancelled']
    notes: str = Field(default='',max_length=3000)
    outcome: str = Field(default='',max_length=1000)
class FollowUpInput(Strict):
    case_id: str
    assigned_to: str
    due_at: datetime
    notes: str = Field(default='',max_length=1000)
class FollowUpUpdate(Strict):
    status: Literal['Scheduled','Contacted','Completed','Missed']
    outcome: str = Field(default='',max_length=1000)
class SupportInput(Strict):
    case_id: str
    kind: str = Field(min_length=2,max_length=150)
    message: str = Field(default='',max_length=3000)
class AlertUpdate(Strict):
    status: Literal['New','Acknowledged','Assigned','In Progress','Resolved','Closed']
    assigned_to: str | None = None
class ChatInput(TextInput):
    case_id: str
