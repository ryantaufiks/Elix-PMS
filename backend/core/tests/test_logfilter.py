import json
import logging
import logging.config
from io import StringIO
from pathlib import Path

from django.test import SimpleTestCase

from myproject.logfilter import RedactSecrets, redact


class RedactTests(SimpleTestCase):
    def test_tokens_in_query_strings_are_blanked(self):
        self.assertEqual(redact('"WebSocket /ws/events/?token=eyJabc.def" [accepted]'), '"WebSocket /ws/events/?token=<redacted>" [accepted]')
        self.assertEqual(redact("/ws/events/?kiosk_token=kio_x1&foo=1"), "/ws/events/?kiosk_token=<redacted>&foo=1")
        self.assertEqual(redact("GET /v1/units/?token_hint=abc"), "GET /v1/units/?token_hint=abc")

    def test_filter_rewrites_record_args(self):
        out = StringIO()
        handler = logging.StreamHandler(out)
        handler.addFilter(RedactSecrets())
        log = logging.getLogger("test.redact")
        log.addHandler(handler)
        log.warning('%s - "WebSocket %s" [accepted]', "1.2.3.4", "/ws/events/?token=secret.jwt")
        self.assertIn("token=<redacted>", out.getvalue())
        self.assertNotIn("secret.jwt", out.getvalue())

    def test_uvicorn_log_config_loads(self):
        config = json.loads((Path(__file__).resolve().parents[2] / "myproject" / "uvicorn-logging.json").read_text())
        logging.config.dictConfig(config)
        self.assertTrue(any(isinstance(f, RedactSecrets) for f in logging.getLogger("uvicorn.access").handlers[0].filters))
