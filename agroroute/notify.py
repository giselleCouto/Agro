"""Notificação de leads por e-mail.

Quando um lead é enviado pelo formulário, avisa o time comercial da NOKAHI
em `contato@nokahi.com` e `giselle@coutofalcao.com`.

Envio via SMTP quando configurado (variáveis de ambiente abaixo); sem SMTP,
apenas registra no log (modo desenvolvimento) — o lead nunca é perdido, pois
já foi gravado no banco antes de tentar notificar.

Variáveis de ambiente:
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD
  SMTP_FROM        (remetente; default no-reply@nokahi.com)
  SMTP_SSL         ("1" para porta 465/SSL; senão STARTTLS)
  LEAD_NOTIFY_EMAILS  (lista separada por vírgula; default abaixo)
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("nokahi.notify")

DEFAULT_RECIPIENTS = ["contato@nokahi.com", "giselle@coutofalcao.com"]


def notify_recipients() -> list[str]:
    raw = os.environ.get("LEAD_NOTIFY_EMAILS")
    if raw:
        return [e.strip() for e in raw.split(",") if e.strip()]
    return list(DEFAULT_RECIPIENTS)


def build_lead_email(lead: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"[NOKAHI] Novo lead: {lead.get('name','?')}" + (
        f" — {lead['company']}" if lead.get("company") else ""
    )
    msg["From"] = os.environ.get("SMTP_FROM", "no-reply@nokahi.com")
    msg["To"] = ", ".join(notify_recipients())
    if lead.get("email"):
        msg["Reply-To"] = lead["email"]
    linhas = [
        "Novo contato recebido pelo site da NOKAHI AgroRoute:",
        "",
        f"Nome:      {lead.get('name','')}",
        f"Empresa:   {lead.get('company','') or '-'}",
        f"E-mail:    {lead.get('email','')}",
        f"Telefone:  {lead.get('phone','') or '-'}",
        f"Cargo:     {lead.get('role','') or '-'}",
        f"Frota:     {lead.get('fleet_size','') or '-'}",
        f"Origem:    {lead.get('source','')}",
        "",
        "Mensagem:",
        (lead.get("message") or "-"),
        "",
        "— Notificação automática NOKAHI AgroRoute",
    ]
    msg.set_content("\n".join(linhas))
    return msg


def _smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def send_lead_notification(lead: dict) -> bool:
    """Envia o e-mail de notificação. Nunca levanta exceção (best-effort)."""
    recipients = notify_recipients()
    try:
        msg = build_lead_email(lead)
    except Exception as e:  # pragma: no cover
        log.error("falha ao montar e-mail de lead: %s", e)
        return False

    if not _smtp_configured():
        log.info("[DEV] lead notificaria %s: %s <%s>",
                 recipients, lead.get("name"), lead.get("email"))
        return False

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    use_ssl = os.environ.get("SMTP_SSL", "").lower() in ("1", "true", "yes")
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        with server:
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        log.info("lead notificado para %s", recipients)
        return True
    except Exception as e:
        log.error("falha ao enviar e-mail de lead: %s", e)
        return False
