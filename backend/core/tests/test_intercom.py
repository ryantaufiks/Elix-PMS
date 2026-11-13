import io
from unittest import mock

import jwt
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from core import assistant
from core import models as m
from core.tasks import expire_call, push_call_ended, push_incoming_call

from .factories import make_condo, make_resident, make_staff, make_unit

LIVEKIT = {"LIVEKIT_URL": "wss://elix-test.livekit.cloud", "LIVEKIT_API_KEY": "APIkey", "LIVEKIT_API_SECRET": "s" * 32}
Status = m.IntercomCall.Status


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "JPEG")
    return SimpleUploadedFile("visitor.jpg", buf.getvalue(), content_type="image/jpeg")


@override_settings(**LIVEKIT)
@mock.patch("core.tasks.end_call_room.delay")
@mock.patch("core.tasks.finish_call.apply_async")
@mock.patch("core.tasks.expire_call.apply_async")
@mock.patch("core.tasks.push_incoming_call.delay")
@mock.patch("core.tasks.open_gate.delay")
class IntercomFlowTests(APITestCase):
    def setUp(self):
        cache.clear()
        # Visitor details and photo are covered in test_visitor_privacy; this suite tests the call flow.
        self.condo = make_condo("alpha", intercom_ring_timeout_seconds=30, kiosk_visitor_form=False,
                                kiosk_photo_required=False)
        # (A photo is still kept when the kiosk sends one with the visitor's consent; see ring().)
        self.unit, self.empty_unit = make_unit(self.condo, "05", "12"), make_unit(self.condo, "09", "01")
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Lobby", gate_type="pedestrian")
        self.kiosk = m.Kiosk(condominium=self.condo, gate=self.gate, name="Lobby kiosk")
        self.kiosk_token = self.kiosk.issue_token()
        self.kiosk.save()
        self.alice = make_resident("alice", self.unit)
        self.bob = make_resident("bob", self.unit)
        self.stranger = make_resident("stranger", self.empty_unit)
        m.Residency.objects.filter(user=self.stranger).update(receives_intercom_calls=False)

    def kiosk_post(self, url, data=None, **kw):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data or {}, HTTP_AUTHORIZATION=f"Kiosk {self.kiosk_token}", **kw)

    def kiosk_get(self, url):
        return self.client.get(url, HTTP_AUTHORIZATION=f"Kiosk {self.kiosk_token}")

    def as_user(self, user, url):
        self.client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)
        self.client.force_authenticate(None)
        return response

    def ring(self, **data):
        response = self.kiosk_post("/v1/kiosk/calls/", {"unit": self.unit.id, "visitor_name": "Grab driver",
                                                        "consent": "true", **data}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_kiosk_auth(self, *mocks):
        self.assertEqual(self.client.get("/v1/kiosk/me/").status_code, 401)
        self.assertEqual(self.client.get("/v1/kiosk/me/", HTTP_AUTHORIZATION="Kiosk kio_wrong").status_code, 401)
        response = self.client.get("/v1/kiosk/me/", HTTP_AUTHORIZATION=f"Kiosk {self.kiosk_token}",
                                   HTTP_X_APP_VERSION="1.2.0")
        self.assertEqual(response.data["gate_name"], "Lobby")
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.app_version, "1.2.0")
        # A user JWT is not a kiosk.
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.get("/v1/kiosk/me/").status_code, 403)

    def test_directory_hides_units_without_call_takers(self, *mocks):
        response = self.client.get("/v1/kiosk/directory/", HTTP_AUTHORIZATION=f"Kiosk {self.kiosk_token}")
        self.assertEqual([u["label"] for u in response.data], ["#05-12"])
        response = self.client.get("/v1/kiosk/directory/?q=%2305-12", HTTP_AUTHORIZATION=f"Kiosk {self.kiosk_token}")
        self.assertEqual(len(response.data), 1)
        self.assertNotIn("alice", str(response.data))

    def test_ring_returns_livekit_token_and_schedules_timeout(self, open_gate, push, expire, finish, end_room):
        response = self.ring(snapshot=jpeg())
        call = m.IntercomCall.objects.get()
        self.assertEqual((call.status, call.gate, call.visitor_name), (Status.RINGING, self.gate, "Grab driver"))
        lk = response.data["livekit"]
        claims = jwt.decode(lk["token"], LIVEKIT["LIVEKIT_API_SECRET"], algorithms=["HS256"])
        self.assertEqual((claims["iss"], claims["sub"]), ("APIkey", f"kiosk-{self.kiosk.pk}"))
        self.assertEqual(claims["video"]["room"], call.room_name)
        self.assertTrue(claims["video"]["roomJoin"])
        push.assert_called_once_with(call.pk)
        expire.assert_called_once_with((call.pk,), countdown=30)
        self.assertTrue(response.data["call"]["has_snapshot"])

    def test_cannot_ring_unit_without_call_takers(self, *mocks):
        response = self.kiosk_post("/v1/kiosk/calls/", {"unit": self.empty_unit.id})
        self.assertEqual(response.status_code, 409)

    def test_cannot_ring_other_condo(self, *mocks):
        other_unit = make_unit(make_condo("beta"))
        make_resident("x", other_unit)
        self.assertEqual(self.kiosk_post("/v1/kiosk/calls/", {"unit": other_unit.id}).status_code, 400)

    @override_settings(LIVEKIT_URL="")
    def test_unconfigured_livekit_rings_nobody(self, open_gate, push, *mocks):
        self.assertEqual(self.kiosk_post("/v1/kiosk/calls/", {"unit": self.unit.id}).status_code, 503)
        self.assertFalse(m.IntercomCall.objects.exists())
        push.assert_not_called()

    def test_answer_then_swipe_to_unlock(self, open_gate, *mocks):
        self.ring()
        call = m.IntercomCall.objects.get()
        response = self.as_user(self.alice, f"/v1/intercom-calls/{call.id}/answer/")
        self.assertEqual(response.status_code, 200, response.data)
        claims = jwt.decode(response.data["livekit"]["token"], LIVEKIT["LIVEKIT_API_SECRET"], algorithms=["HS256"])
        self.assertEqual((claims["sub"], claims["video"]["room"]), (f"user-{self.alice.pk}", call.room_name))
        # Second phone in the household loses the race.
        self.assertEqual(self.as_user(self.bob, f"/v1/intercom-calls/{call.id}/answer/").status_code, 409)

        response = self.as_user(self.alice, f"/v1/intercom-calls/{call.id}/unlock/")
        self.assertEqual(response.status_code, 202)
        call.refresh_from_db()
        self.assertEqual((call.status, call.decided_by), (Status.APPROVED, self.alice))
        log = m.AccessLog.objects.get()
        self.assertEqual((log.method, log.result, log.gate, log.actor, log.intercom_call),
                         ("intercom", "granted", self.gate, self.alice, call))
        open_gate.assert_called_once_with(log.pk)
        # Unlocking twice does not open the gate twice.
        self.assertEqual(self.as_user(self.alice, f"/v1/intercom-calls/{call.id}/unlock/").status_code, 409)
        self.assertEqual(open_gate.call_count, 1)

    def test_unlock_straight_from_preview(self, open_gate, *mocks):
        self.ring()
        call = m.IntercomCall.objects.get()
        self.assertEqual(self.as_user(self.bob, f"/v1/intercom-calls/{call.id}/unlock/").status_code, 202)
        call.refresh_from_db()
        self.assertEqual((call.status, call.answered_by), (Status.APPROVED, self.bob))

    def test_other_residents_cannot_act(self, open_gate, *mocks):
        self.ring()
        call = m.IntercomCall.objects.get()
        self.assertEqual(self.as_user(self.stranger, f"/v1/intercom-calls/{call.id}/unlock/").status_code, 404)
        open_gate.assert_not_called()

    def test_security_can_unlock(self, open_gate, *mocks):
        guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        self.ring()
        call = m.IntercomCall.objects.get()
        self.assertEqual(self.as_user(guard, f"/v1/intercom-calls/{call.id}/unlock/").status_code, 202)

    def test_reject_logs_denial_and_ends_room(self, open_gate, push, expire, finish, end_room):
        self.ring()
        call = m.IntercomCall.objects.get()
        self.assertEqual(self.as_user(self.alice, f"/v1/intercom-calls/{call.id}/reject/").data["status"], "rejected")
        self.assertEqual(m.AccessLog.objects.get().result, "denied")
        end_room.assert_called_with(call.room_name)
        self.assertEqual(self.as_user(self.alice, f"/v1/intercom-calls/{call.id}/unlock/").status_code, 409)
        open_gate.assert_not_called()

    def test_timeout_marks_missed(self, *mocks):
        self.ring()
        call = m.IntercomCall.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            expire_call(call.pk)
        call.refresh_from_db()
        self.assertEqual(call.status, Status.MISSED)
        self.assertEqual(self.as_user(self.alice, f"/v1/intercom-calls/{call.id}/answer/").status_code, 409)

    def test_new_call_cancels_previous_one_from_same_kiosk(self, *mocks):
        self.ring()
        self.ring()
        self.assertEqual(sorted(m.IntercomCall.objects.values_list("status", flat=True)), ["cancelled", "ringing"])

    def test_kiosk_hangup(self, *mocks):
        call_id = self.ring().data["call"]["id"]
        self.assertEqual(self.kiosk_post(f"/v1/kiosk/calls/{call_id}/hangup/").data["status"], "cancelled")

    def test_hangup_after_answer_blocks_unlock(self, open_gate, *mocks):
        call_id = self.ring().data["call"]["id"]
        self.as_user(self.alice, f"/v1/intercom-calls/{call_id}/answer/")
        self.assertEqual(self.kiosk_post(f"/v1/kiosk/calls/{call_id}/hangup/").status_code, 200)
        self.assertEqual(self.as_user(self.alice, f"/v1/intercom-calls/{call_id}/unlock/").status_code, 409)

    def test_guardhouse_call_rings_staff_only(self, open_gate, push, *mocks):
        guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        response = self.kiosk_post("/v1/kiosk/calls/", {"guardhouse": "true", "visitor_name": "Kept out"})
        self.assertEqual(response.status_code, 201, response.data)
        call = m.IntercomCall.objects.get()
        self.assertEqual((call.unit, call.visitor_name, response.data["call"]["unit_display"]), (None, "", "Guardhouse"))
        push.assert_not_called()  # Nobody's phone rings; the dashboard does.
        self.assertEqual(self.as_user(self.alice, f"/v1/intercom-calls/{call.id}/answer/").status_code, 404)
        self.assertEqual(self.as_user(guard, f"/v1/intercom-calls/{call.id}/answer/").status_code, 200)
        self.assertEqual(self.as_user(guard, f"/v1/intercom-calls/{call.id}/unlock/").status_code, 202)
        call.refresh_from_db()
        self.assertEqual(call.status, Status.APPROVED)
        self.assertFalse(call.visits.exists())
        self.assertEqual(self.kiosk_get(f"/v1/kiosk/calls/{call.id}/pass/").status_code, 404)
        open_gate.assert_called_once()

    def test_guardhouse_call_follows_site_setting(self, *mocks):
        self.assertTrue(self.kiosk_get("/v1/kiosk/me/").data["call_guardhouse"])
        self.condo.kiosk_call_guardhouse = False
        self.condo.save()
        self.assertFalse(self.kiosk_get("/v1/kiosk/me/").data["call_guardhouse"])
        self.assertEqual(self.kiosk_post("/v1/kiosk/calls/", {"guardhouse": "true"}).status_code, 409)
        # A unit is still needed for an ordinary call.
        self.assertEqual(self.kiosk_post("/v1/kiosk/calls/", {}).status_code, 400)

    def test_assistant_can_call_the_guardhouse(self, *mocks):
        self.assertIn("call_guardhouse", [t["name"] for t in assistant.tools(self.condo)])
        self.assertIn("call_guardhouse", assistant.instructions(self.condo))
        self.assertEqual(assistant.action("call_guardhouse", "{}"), {"type": "call_guardhouse"})
        self.condo.kiosk_call_guardhouse = False
        self.condo.save()
        self.assertNotIn("call_guardhouse", [t["name"] for t in assistant.tools(self.condo)])
        self.assertNotIn("call_guardhouse", assistant.instructions(self.condo))

    def test_snapshot_only_for_the_unit(self, *mocks):
        call_id = self.ring(snapshot=jpeg()).data["call"]["id"]
        self.client.force_authenticate(self.alice)
        response = self.client.get(f"/v1/intercom-calls/{call_id}/snapshot/")
        self.assertEqual((response.status_code, response["Cache-Control"]), (200, "private, no-store"))
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(f"/v1/intercom-calls/{call_id}/snapshot/").status_code, 404)

    @override_settings(REST_FRAMEWORK={**__import__("django.conf").conf.settings.REST_FRAMEWORK,
                                       "DEFAULT_THROTTLE_RATES": {"kiosk_call": "2/min"}})
    def test_kiosk_call_rate_limit(self, *mocks):
        self.ring(); self.ring()
        self.assertEqual(self.kiosk_post("/v1/kiosk/calls/", {"unit": self.unit.id}).status_code, 429)


class PushTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)

    def test_register_device_moves_token_between_users(self):
        self.client.force_authenticate(self.alice)
        response = self.client.post("/v1/push-devices/", {"platform": "android", "token": "tok-1"})
        self.assertEqual(response.status_code, 201)
        bob = make_resident("bob", self.unit)
        self.client.force_authenticate(bob)
        self.assertEqual(self.client.post("/v1/push-devices/", {"platform": "android", "token": "tok-1"}).status_code, 200)
        self.assertEqual(m.PushDevice.objects.get().user, bob)
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.get("/v1/push-devices/").data["count"], 0)

    @override_settings(FCM_SERVICE_ACCOUNT_FILE="/tmp/sa.json")
    @mock.patch("core.push._access_token", return_value=("fcm-token", "elix-project"))
    @mock.patch("core.push.requests.post")
    def test_call_ended_push_is_silent_data_only(self, post, token):
        m.PushDevice.objects.create(user=self.alice, platform="ios", token="phone")
        call = m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, room_name="r2", status="missed")
        post.return_value = mock.Mock(ok=True, status_code=200, text="")
        self.assertEqual(push_call_ended(call.pk), 1)
        message = post.call_args.kwargs["json"]["message"]
        self.assertEqual(message["data"], {"type": "intercom_call_ended", "call_id": str(call.pk), "status": "missed"})
        self.assertEqual(message["apns"]["payload"], {"aps": {"content-available": 1}})

    @override_settings(FCM_SERVICE_ACCOUNT_FILE="/tmp/sa.json")
    @mock.patch("core.push._access_token", return_value=("fcm-token", "elix-project"))
    @mock.patch("core.push.requests.post")
    def test_push_goes_to_call_takers_and_drops_dead_tokens(self, post, token):
        m.PushDevice.objects.create(user=self.alice, platform="android", token="live")
        m.PushDevice.objects.create(user=self.alice, platform="ios", token="dead")
        muted = make_resident("muted", self.unit)
        m.Residency.objects.filter(user=muted).update(receives_intercom_calls=False)
        m.PushDevice.objects.create(user=muted, platform="android", token="muted")
        kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby")
        call = m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, kiosk=kiosk, room_name="r1")

        def reply(url, json, **kw):
            dead = json["message"]["token"] == "dead"
            return mock.Mock(ok=not dead, status_code=404 if dead else 200,
                             text='{"error":{"status":"NOT_FOUND","details":[{"errorCode":"UNREGISTERED"}]}}')
        post.side_effect = reply

        self.assertEqual(push_incoming_call(call.pk), 1)
        self.assertEqual(post.call_args_list[0].args[0], "https://fcm.googleapis.com/v1/projects/elix-project/messages:send")
        sent_to = {c.kwargs["json"]["message"]["token"] for c in post.call_args_list}
        self.assertEqual(sent_to, {"live", "dead"})
        message = post.call_args_list[0].kwargs["json"]["message"]
        self.assertEqual((message["data"]["type"], message["android"]["priority"]), ("intercom_call", "high"))
        self.assertEqual(set(m.PushDevice.objects.values_list("token", flat=True)), {"live", "muted"})

    def test_push_disabled_without_credentials(self):
        call = m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, room_name="r2")
        self.assertEqual(push_incoming_call(call.pk), 0)
