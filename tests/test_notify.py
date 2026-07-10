"""Testa a notificação de leads por e-mail (destinatários e disparo)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute import api as api_mod
from agroroute import notify
from agroroute.api import app

client = TestClient(app)


def test_recipients_include_both_addresses(monkeypatch):
    monkeypatch.delenv("LEAD_NOTIFY_EMAILS", raising=False)
    r = notify.notify_recipients()
    assert "contato@nokahi.com" in r
    assert "giselle@coutofalcao.com" in r


def test_email_has_both_recipients_and_lead_data(monkeypatch):
    monkeypatch.delenv("LEAD_NOTIFY_EMAILS", raising=False)
    msg = notify.build_lead_email({"name": "Ana", "company": "Usina X",
                                   "email": "ana@x.com", "message": "olá"})
    assert "contato@nokahi.com" in msg["To"]
    assert "giselle@coutofalcao.com" in msg["To"]
    assert msg["Reply-To"] == "ana@x.com"
    assert "Ana" in msg.get_content() and "Usina X" in msg.get_content()


def test_send_without_smtp_does_not_raise(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert notify.send_lead_notification({"name": "Ana", "email": "ana@x.com"}) is False


def test_lead_endpoint_schedules_notification(monkeypatch):
    sent = {}

    def fake_send(lead):
        sent["lead"] = lead
        return True

    monkeypatch.setattr(api_mod, "send_lead_notification", fake_send)
    r = client.post("/v1/leads", json={"name": "Bruno", "email": "bruno@usina.com"})
    assert r.status_code == 200
    assert sent["lead"]["email"] == "bruno@usina.com"


def test_honeypot_does_not_notify(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(api_mod, "send_lead_notification", lambda lead: called.__setitem__("n", called["n"] + 1))
    r = client.post("/v1/leads", json={"name": "bot", "email": "b@b.com", "website": "http://spam"})
    assert r.status_code == 200
    assert called["n"] == 0
