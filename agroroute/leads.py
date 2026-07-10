"""Captura de leads (formulário de contato da landing).

Grava no banco (tabela `leads`) e oferece listagem protegida por token de
admin para o time comercial da NOKAHI dar sequência ao contato.

Anti-spam: honeypot (campo oculto `website`) + limite simples por IP.
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque

from pydantic import BaseModel, Field, field_validator

from .db import LeadRow, session_factory, write_lock

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LeadIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    company: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    role: str | None = Field(default=None, max_length=120)
    fleet_size: str | None = Field(default=None, max_length=40)
    message: str | None = Field(default=None, max_length=2000)
    source: str = Field(default="landing", max_length=40)
    website: str | None = None   # honeypot: se preenchido, é bot

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not EMAIL_RE.match(v.strip()):
            raise ValueError("e-mail inválido")
        return v.strip().lower()


class _RateLimiter:
    """Janela deslizante em memória: N eventos por IP a cada `window` s.

    Poda entradas expiradas e limita o total de IPs rastreados para não crescer
    indefinidamente (proteção contra exaustão de memória por IPs forjados).
    """

    def __init__(self, limit: int = 5, window: int = 60, max_ips: int = 10000):
        self.limit = limit
        self.window = window
        self.max_ips = max_ips
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        for ip in list(self._hits.keys()):
            dq = self._hits[ip]
            while dq and now - dq[0] > self.window:
                dq.popleft()
            if not dq:
                del self._hits[ip]

    def allow(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            # limpa oportunisticamente quando o mapa cresce
            if len(self._hits) > self.max_ips:
                self._prune(now)
            dq = self._hits[ip]
            while dq and now - dq[0] > self.window:
                dq.popleft()
            if len(dq) >= self.limit:
                return False  # entrada mantida, mas limitada e expira sozinha
            dq.append(now)
            return True


class LeadStore:
    def __init__(self, engine=None):
        self._Session = session_factory(engine)
        self.rate = _RateLimiter(limit=5, window=60)

    def create(self, lead: LeadIn, ip: str | None = None) -> dict | None:
        """Grava o lead. Devolve None se for spam (honeypot)."""
        if lead.website:  # honeypot preenchido -> bot; descarta silenciosamente
            return None
        with write_lock(), self._Session() as s:
            row = LeadRow(
                name=lead.name.strip(),
                email=lead.email,
                company=(lead.company or "").strip() or None,
                phone=(lead.phone or "").strip() or None,
                role=(lead.role or "").strip() or None,
                fleet_size=(lead.fleet_size or "").strip() or None,
                message=(lead.message or "").strip() or None,
                source=lead.source or "landing",
                ip=ip,
                status="novo",
            )
            s.add(row)
            s.commit()
            s.refresh(row)  # carrega id e created_at gerados pelo banco
            return row.to_dict()

    def list(self, limit: int = 200, status: str | None = None) -> list[dict]:
        with self._Session() as s:
            q = s.query(LeadRow).order_by(LeadRow.created_at.desc())
            if status:
                q = q.filter(LeadRow.status == status)
            return [r.to_dict() for r in q.limit(limit).all()]

    def set_status(self, lead_id: int, status: str) -> bool:
        with write_lock(), self._Session() as s:
            row = s.get(LeadRow, lead_id)
            if not row:
                return False
            row.status = status
            s.commit()
            return True

    def count(self) -> int:
        with self._Session() as s:
            return s.query(LeadRow).count()
