"""Keeps sign-in tokens out of the logs.

The WebSocket carries the JWT (or kiosk token) in its query string, and uvicorn logs each request's
path with the query. This filter blanks those values before a line is written.
"""
import logging
import re

SECRET_QUERY = re.compile(r"((?:^|[?&])(?:token|kiosk_token|auth_key)=)[^&\s\"']+")


def redact(text: str) -> str:
    return SECRET_QUERY.sub(r"\1<redacted>", text)


class RedactSecrets(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True
