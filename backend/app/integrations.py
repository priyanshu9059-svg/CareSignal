"""External outreach adapters. Soft-fail: in-app notify always succeeds."""
from __future__ import annotations
import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger('caresignal.outreach')

class SupportAdapter(Protocol):
    def submit(self, reference: str, service: str, **kwargs) -> dict: ...

class MockProvider:
    def submit(self, reference: str, service: str, **kwargs) -> dict:
        return {'reference': reference, 'service': service, 'provider': type(self).__name__,
                'status': 'simulated', 'external_delivery': False}

class MockNHAAAdapter(MockProvider): pass
class MockSMSAdapter(MockProvider): pass
class MockIVRSAdapter(MockProvider): pass
class MockCounsellingAdapter(MockProvider): pass
class MockLegalSupportAdapter(MockProvider): pass
class MockRehabilitationAdapter(MockProvider): pass
class MockNotificationAdapter(MockProvider): pass

class LogSMSAdapter:
    """Demo-friendly SMS: logs the payload (no carrier). Treat as delivered for demo evidence."""
    def submit(self, reference: str, service: str, **kwargs) -> dict:
        to = kwargs.get('to') or os.getenv('STAFF_ALERT_SMS_TO') or 'unconfigured'
        body = kwargs.get('body') or service
        logger.info('SMS outreach case=%s to=%s body=%s', reference, to, body[:200])
        return {'reference': reference, 'service': service, 'provider': 'LogSMSAdapter',
                'status': 'logged', 'external_delivery': True, 'to': to, 'channel': 'sms'}

class LogEmailAdapter:
    def submit(self, reference: str, service: str, **kwargs) -> dict:
        to = kwargs.get('to') or 'unconfigured'
        subject = kwargs.get('subject') or service
        body = kwargs.get('body') or service
        logger.info('Email outreach case=%s to=%s subject=%s', reference, to, subject)
        return {'reference': reference, 'service': service, 'provider': 'LogEmailAdapter',
                'status': 'logged', 'external_delivery': True, 'to': to, 'channel': 'email', 'subject': subject}

class SmtpEmailAdapter:
    def submit(self, reference: str, service: str, **kwargs) -> dict:
        host = os.getenv('SMTP_HOST')
        to = kwargs.get('to')
        if not host or not to:
            return LogEmailAdapter().submit(reference, service, **kwargs)
        port = int(os.getenv('SMTP_PORT', '587'))
        user = os.getenv('SMTP_USER', '')
        password = os.getenv('SMTP_PASSWORD', '')
        sender = os.getenv('SMTP_FROM', user or 'caresignal@localhost')
        msg = EmailMessage()
        msg['Subject'] = kwargs.get('subject') or service
        msg['From'] = sender
        msg['To'] = to
        msg.set_content(kwargs.get('body') or service)
        try:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if os.getenv('SMTP_TLS', 'true').lower() == 'true':
                    smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
            return {'reference': reference, 'service': service, 'provider': 'SmtpEmailAdapter',
                    'status': 'sent', 'external_delivery': True, 'to': to, 'channel': 'email'}
        except Exception as exc:
            logger.warning('SMTP send failed: %s', type(exc).__name__)
            return {'reference': reference, 'service': service, 'provider': 'SmtpEmailAdapter',
                    'status': 'failed', 'external_delivery': False, 'error': type(exc).__name__, 'to': to}

class WebhookAdapter:
    def submit(self, reference: str, service: str, **kwargs) -> dict:
        url = os.getenv('OUTREACH_WEBHOOK_URL')
        if not url:
            return {'reference': reference, 'service': service, 'provider': 'WebhookAdapter',
                    'status': 'skipped', 'external_delivery': False}
        payload = json.dumps({'reference': reference, 'service': service, **kwargs}).encode()
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {'reference': reference, 'service': service, 'provider': 'WebhookAdapter',
                        'status': 'sent', 'external_delivery': True, 'http_status': resp.status}
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning('Webhook outreach failed: %s', type(exc).__name__)
            return {'reference': reference, 'service': service, 'provider': 'WebhookAdapter',
                    'status': 'failed', 'external_delivery': False, 'error': type(exc).__name__}

def sms_adapter() -> SupportAdapter:
    mode = (os.getenv('SMS_PROVIDER') or 'mock').lower()
    if mode in {'log', 'demo'}:
        return LogSMSAdapter()
    if mode == 'webhook':
        return WebhookAdapter()
    return MockSMSAdapter()

def email_adapter() -> SupportAdapter:
    mode = (os.getenv('EMAIL_PROVIDER') or 'mock').lower()
    if mode == 'smtp':
        return SmtpEmailAdapter()
    if mode in {'log', 'demo'}:
        return LogEmailAdapter()
    if mode == 'webhook':
        return WebhookAdapter()
    return MockNotificationAdapter()
