from typing import Protocol

class SupportAdapter(Protocol):
    def submit(self, reference: str, service: str) -> dict: ...

class MockProvider:
    def submit(self, reference: str, service: str) -> dict:
        return {'reference':reference,'service':service,'provider':type(self).__name__,
                'status':'simulated','external_delivery':False}

class MockNHAAAdapter(MockProvider): pass
class MockSMSAdapter(MockProvider): pass
class MockIVRSAdapter(MockProvider): pass
class MockCounsellingAdapter(MockProvider): pass
class MockLegalSupportAdapter(MockProvider): pass
class MockRehabilitationAdapter(MockProvider): pass
class MockNotificationAdapter(MockProvider): pass
