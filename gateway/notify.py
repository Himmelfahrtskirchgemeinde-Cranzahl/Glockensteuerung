"""
E-Mail-Benachrichtigung bei Fehlern (automatisches Log-System).

Sendet bei Fehlern eine E-Mail an EMAIL_TO (Standard: josua.hess@icloud.com).
Konfiguration per .env (SMTP eines beliebigen Postausgangs):
    SMTP_HOST, SMTP_PORT (Standard 587), SMTP_USER, SMTP_PASS
    SMTP_TLS=1 (STARTTLS, Standard) oder SMTP_SSL=1 (Port 465)
    EMAIL_FROM (Standard = SMTP_USER), EMAIL_TO (Standard josua.hess@icloud.com)

Ist kein SMTP_HOST gesetzt, bleibt der Notifier still (kein Absturz) und
protokolliert einmalig einen Hinweis.
"""
from __future__ import annotations
import logging
import os
import smtplib
import time
from email.message import EmailMessage
from email.utils import formatdate

import tls

log = logging.getLogger("voco-gateway")
DEFAULT_TO = "josua.hess@icloud.com"


class EmailNotifier:
    def __init__(self):
        self.host = os.environ.get("SMTP_HOST", "").strip()
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ.get("SMTP_USER", "").strip()
        self.password = os.environ.get("SMTP_PASS", "")
        self.use_ssl = os.environ.get("SMTP_SSL", "").strip().lower() in ("1", "true", "yes")
        self.use_tls = os.environ.get("SMTP_TLS", "1").strip().lower() in ("1", "true", "yes")
        self.mail_from = os.environ.get("EMAIL_FROM", self.user or "voco-gateway@localhost").strip()
        self.mail_to = os.environ.get("EMAIL_TO", DEFAULT_TO).strip()
        self.min_interval = int(os.environ.get("EMAIL_MIN_INTERVAL", "3600"))  # Spam-Sperre je Betreff
        self._last: dict[str, float] = {}
        self._warned = False

    @property
    def enabled(self) -> bool:
        return bool(self.host)

    def notify(self, subject: str, body: str, dedup_key: str | None = None):
        if not self.enabled:
            if not self._warned:
                log.info("E-Mail-Benachrichtigung nicht konfiguriert (SMTP_HOST fehlt) – Fehler nur im Log.")
                self._warned = True
            return
        key = dedup_key or subject
        now = time.time()
        if now - self._last.get(key, 0) < self.min_interval:
            return  # kürzlich schon gemeldet
        self._last[key] = now
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[Glockensteuerung] {subject}"
            msg["From"] = self.mail_from
            msg["To"] = self.mail_to
            msg["Date"] = formatdate(localtime=True)
            msg.set_content(body)
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.host, self.port, context=tls.context(), timeout=20) as s:
                    self._login_send(s, msg)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=20) as s:
                    if self.use_tls:
                        s.starttls(context=tls.context())
                    self._login_send(s, msg)
            log.info("Fehler-E-Mail an %s gesendet: %s", self.mail_to, subject)
        except Exception as e:
            log.warning("E-Mail-Versand fehlgeschlagen: %s", e)

    def _login_send(self, s: smtplib.SMTP, msg: EmailMessage):
        if self.user:
            s.login(self.user, self.password)
        s.send_message(msg)

    def log_handler(self) -> logging.Handler:
        """Logging-Handler, der ERROR-Meldungen automatisch per Mail verschickt."""
        notifier = self

        class _H(logging.Handler):
            def emit(self, record: logging.LogRecord):
                try:
                    body = self.format(record)
                    notifier.notify(record.getMessage()[:120], body, dedup_key=record.getMessage()[:60])
                except Exception:
                    pass

        h = _H(level=logging.ERROR)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s\n\n%(message)s"))
        return h
