import base64
import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core import models as m
from core import relays

from .factories import make_condo
from .fake_shelly import FakeShelly

Mode = m.RelayController.ControlMode


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


class RelayTestBase(TestCase):
    def setUp(self):
        self.condo = make_condo()
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main")

    def relay(self, provider=m.Provider.SHELLY, **kw):
        return m.RelayController.objects.create(gate=self.gate, name="Barrier", provider=provider, **kw)


class ShellyLocalTests(RelayTestBase):
    def test_pulse_with_digest_auth_sends_toggle_after(self):
        with FakeShelly(password="rahasia") as device:
            relay = self.relay(control_mode=Mode.LOCAL, local_ip="127.0.0.1", local_port=device.port,
                               local_password="rahasia", pulse_seconds=3)
            result = relays.pulse(relay)
        self.assertEqual(result.via, "local")
        self.assertEqual(device.calls[-1]["method"], "Switch.Set")
        self.assertEqual(device.calls[-1]["params"], {"id": 0, "on": True, "toggle_after": 3})

    def test_wrong_password_is_reported(self):
        with FakeShelly(password="rahasia") as device:
            relay = self.relay(control_mode=Mode.LOCAL, local_ip="127.0.0.1", local_port=device.port,
                               local_password="salah")
            with self.assertRaisesMessage(relays.RelayError, "401"):
                relays.pulse(relay)

    def test_status(self):
        with FakeShelly() as device:
            relay = self.relay(control_mode=Mode.LOCAL, local_ip="127.0.0.1", local_port=device.port)
            self.assertEqual(relays.status(relay).detail, "off")

    def test_gen1_fallback(self):
        with FakeShelly(gen1=True) as device:
            relay = self.relay(control_mode=Mode.LOCAL, local_ip="127.0.0.1", local_port=device.port, pulse_seconds=2)
            relays.pulse(relay)
        self.assertIn("turn=on", device.calls[-1]["gen1"])
        self.assertIn("timer=2", device.calls[-1]["gen1"])

    def test_unreachable_device(self):
        relay = self.relay(control_mode=Mode.LOCAL, local_ip="127.0.0.1", local_port=1)
        with self.assertRaisesMessage(relays.RelayError, "Cannot reach"):
            relays.pulse(relay)


class ShellyCloudTests(RelayTestBase):
    def setUp(self):
        super().setUp()
        self.account = m.IntegrationAccount.objects.create(
            condominium=self.condo, provider=m.Provider.SHELLY, label="Cloud",
            shelly_server_uri="https://shelly-103-eu.shelly.cloud/", shelly_auth_key="AUTHKEY",
        )

    @mock.patch("core.relays.base.requests.request", return_value=FakeResponse(200))
    def test_cloud_pulse(self, request):
        relay = self.relay(account=self.account, cloud_device_id="a0b1c2", channel=0, pulse_seconds=3)
        self.assertEqual(relays.pulse(relay).via, "cloud")
        method, url = request.call_args.args
        self.assertEqual((method, url), ("POST", "https://shelly-103-eu.shelly.cloud/v2/devices/api/set/switch"))
        self.assertEqual(request.call_args.kwargs["params"], {"auth_key": "AUTHKEY"})
        self.assertEqual(request.call_args.kwargs["json"], {"id": "a0b1c2", "channel": 0, "on": True, "toggle_after": 3})

    @mock.patch("core.relays.base.requests.request",
                return_value=FakeResponse(400, {"error": "DEVICE_OFFLINE", "data": {"messages": ["Device is offline"]}}))
    def test_cloud_error_message(self, request):
        relay = self.relay(account=self.account, cloud_device_id="a0b1c2")
        with self.assertRaisesMessage(relays.RelayError, "DEVICE_OFFLINE"):
            relays.pulse(relay)

    def test_local_then_cloud_falls_back(self):
        relay = self.relay(account=self.account, cloud_device_id="a0b1c2", control_mode=Mode.LOCAL_THEN_CLOUD,
                           local_ip="127.0.0.1", local_port=1)
        with mock.patch("core.relays.shelly.http", wraps=relays.shelly.http) as spy:
            def fake(method, url, **kw):
                if "127.0.0.1" in url:
                    raise relays.RelayError("Cannot reach local")
                return FakeResponse(200)
            spy.side_effect = fake
            result = relays.pulse(relay)
        self.assertEqual(result.via, "cloud")
        self.assertIn("local failed", result.detail)


class EwelinkCloudTests(RelayTestBase):
    def setUp(self):
        super().setUp()
        self.account = m.IntegrationAccount.objects.create(
            condominium=self.condo, provider=m.Provider.EWELINK, label="eWeLink", ewelink_app_id="APPID",
            ewelink_app_secret="APPSECRET", ewelink_access_token="old-at", ewelink_refresh_token="old-rt",
            ewelink_token_expires_at=timezone.now() + timedelta(days=10),
        )

    def test_pulse_uses_bearer_token(self):
        relay = self.relay(provider=m.Provider.EWELINK, account=self.account, cloud_device_id="1000abc")
        with mock.patch("core.relays.base.requests.request", return_value=FakeResponse(200, {"error": 0, "data": {}})) as request:
            relays.pulse(relay)
        kwargs = request.call_args.kwargs
        self.assertEqual(request.call_args.args[1], "https://as-apia.coolkit.cc/v2/device/thing/status")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer old-at")
        self.assertEqual(kwargs["json"], {"type": 1, "id": "1000abc", "params": {"switch": "on"}})

    def test_expired_token_is_refreshed_with_signature(self):
        relay = self.relay(provider=m.Provider.EWELINK, account=self.account, cloud_device_id="1000abc", channel=2)
        responses = iter([
            FakeResponse(200, {"error": 401, "msg": "token expired"}),
            FakeResponse(200, {"error": 0, "data": {"at": "new-at", "rt": "new-rt"}}),
            FakeResponse(200, {"error": 0, "data": {}}),
        ])
        with mock.patch("core.relays.base.requests.request", side_effect=lambda *a, **k: next(responses)) as request:
            relays.pulse(relay)
        refresh = request.call_args_list[1]
        expected = base64.b64encode(hmac.new(b"APPSECRET", refresh.kwargs["data"].encode(), hashlib.sha256).digest())
        self.assertEqual(refresh.kwargs["headers"]["Authorization"], f"Sign {expected.decode()}")
        self.assertEqual(json.loads(refresh.kwargs["data"]), {"rt": "old-rt"})
        self.assertEqual(request.call_args_list[2].kwargs["headers"]["Authorization"], "Bearer new-at")
        self.assertEqual(request.call_args_list[2].kwargs["json"]["params"],
                         {"switches": [{"switch": "on", "outlet": 2}]})
        self.account.refresh_from_db()
        self.assertEqual((self.account.ewelink_access_token, self.account.ewelink_refresh_token), ("new-at", "new-rt"))
