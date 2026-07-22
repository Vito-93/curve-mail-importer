from __future__ import annotations

import email
import imaplib
import logging
from dataclasses import dataclass
from email.message import Message

logger = logging.getLogger(__name__)


@dataclass
class RawEmail:
    uid: bytes
    subject: str
    body: str


def _extract_text_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    from bs4 import BeautifulSoup
                    html = payload.decode(charset, errors="replace")
                    return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            ct = msg.get_content_type()
            text = payload.decode(charset, errors="replace")
            if ct == "text/html":
                from bs4 import BeautifulSoup
                return BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
            return text
    return ""


class ImapGateway:

    def __init__(self, host: str, port: int, user: str, password: str) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._conn: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        self._conn = imaplib.IMAP4_SSL(self._host, self._port)
        self._conn.login(self._user, self._password)
        logger.info("IMAP connected to %s as %s", self._host, self._user)

    def reconnect(self) -> None:
        logger.info("Reconnecting to IMAP server...")
        self.disconnect()
        self.connect()

    def fetch_unseen(self, folder: str) -> list[RawEmail]:
        if self._conn is None:
            raise RuntimeError("Not connected")

        status, _ = self._conn.select(f'"{folder}"')
        if status != "OK":
            available = self._conn.list()[1]
            folders = [f.decode() for f in available if available] if available else []
            logger.error("Cannot select folder %r. Available: %s", folder, folders)
            raise RuntimeError(f"IMAP folder {folder!r} not found")
        _, data = self._conn.uid("search", None, "UNSEEN")
        uids = data[0].split() if data[0] else []

        if not uids:
            return []

        logger.info("Found %d unseen emails in %s", len(uids), folder)
        results: list[RawEmail] = []
        for uid in uids:
            _, msg_data = self._conn.uid("fetch", uid, "(RFC822)")
            if msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            subject = msg.get("Subject", "")
            body = _extract_text_body(msg)
            results.append(RawEmail(uid=uid, subject=subject, body=body))

        return results

    def mark_seen(self, uids: list[bytes]) -> None:
        if self._conn is None:
            raise RuntimeError("Not connected")
        for uid in uids:
            self._conn.uid("store", uid, "+FLAGS", "\\Seen")

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.close()
                self._conn.logout()
            except Exception:
                pass
            self._conn = None
