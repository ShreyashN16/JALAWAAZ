"""SMS behind one function. SMS_PROVIDER=console prints and logs; swap in a real provider later.
No real SMS is sent in this prototype."""
from __future__ import annotations

import logging

from .. import db
from ..config import settings

log = logging.getLogger("jalawaaz.sms")


def send_sms(to_role: str, ticket_id: int | None, body: str) -> None:
    if settings.SMS_PROVIDER == "console":
        log.info("[SMS simulated -> %s] %s", to_role, body)
    con = db.connect()
    try:
        con.execute("INSERT INTO sms_log(at, to_role, ticket_id, body) VALUES (?,?,?,?)", (db.ts(), to_role, ticket_id, body))
    finally:
        con.close()
