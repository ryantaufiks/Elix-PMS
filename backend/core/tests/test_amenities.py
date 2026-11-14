import hashlib
import hmac
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.test import APITestCase

from core import bookings, visits
from core import models as m

from .factories import make_condo, make_resident, make_staff, make_unit, set_plan

SG = ZoneInfo("Asia/Singapore")


def at(days, hour):
    """A slot start ``days`` from today (Singapore), at ``hour``:00."""
    return datetime.combine(timezone.localdate() + timedelta(days=days), time(hour), tzinfo=SG)


def hitpay_response(status_code=201, **body):
    return mock.Mock(status_code=status_code, json=lambda: body, text=str(body))


@mock.patch("core.bookings.broadcast")
class BookingTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.other_unit = make_unit(self.condo, floor="07", number="01")
        self.alice = make_resident("alice", self.unit)
        self.bob = make_resident("bob", self.other_unit)
        self.admin = make_staff("admin", self.condo, m.StaffAssignment.Role.ADMIN)
        self.guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)
        self.bbq = m.Facility.objects.create(condominium=self.condo, name="BBQ pit", opens_at=time(10), closes_at=time(22),
                                             slot_minutes=120, max_slots_per_booking=2, capacity=20)
        self.client.force_authenticate(self.alice)

    def book(self, starts_at, facility=None, **extra):
        return self.client.post("/v1/bookings/", {"facility": (facility or self.bbq).pk, "starts_at": starts_at.isoformat(),
                                                  **extra}, format="json")

    def test_availability(self, _):
        data = self.client.get(f"/v1/facilities/{self.bbq.pk}/availability/", {"date": at(1, 0).date().isoformat()}).data
        self.assertEqual(len(data["slots"]), 6)  # 10:00–22:00 in 2-hour slots.
        self.assertTrue(all(s["available"] for s in data["slots"]))
        self.book(at(1, 12))
        slots = self.client.get(f"/v1/facilities/{self.bbq.pk}/availability/", {"date": at(1, 0).date().isoformat()}).data["slots"]
        self.assertEqual([s["available"] for s in slots], [True, False, True, True, True, True])
        far = self.client.get(f"/v1/facilities/{self.bbq.pk}/availability/", {"date": at(30, 0).date().isoformat()}).data
        self.assertFalse(any(s["available"] for s in far["slots"]))
        self.bbq.open_days = [at(2, 0).weekday()]
        self.bbq.save()
        self.assertFalse(self.client.get(f"/v1/facilities/{self.bbq.pk}/availability/", {"date": at(1, 0).date().isoformat()}).data["open"])

    def test_free_booking_rules(self, _):
        response = self.book(at(1, 12), slots=2, guests=8)
        self.assertEqual(response.status_code, 201, response.data)
        booking = response.data["booking"]
        self.assertEqual((booking["status"], booking["payment_status"], booking["amount"]), ("confirmed", "none", "0.00"))
        self.assertEqual(response.data["payment_url"], "")
        self.client.force_authenticate(self.bob)
        self.assertIn("just been booked", self.book(at(1, 14)).data["detail"])  # Overlaps 12:00–16:00.
        self.assertEqual(self.book(at(1, 16)).status_code, 201)
        self.assertEqual(self.book(at(1, 18), slots=3).status_code, 409)  # Max 2 slots.
        self.assertEqual(self.book(at(1, 21)).status_code, 409)  # Not a slot start.
        self.assertEqual(self.book(at(1, 20), slots=2).status_code, 409)  # Past closing time.
        self.assertEqual(self.book(at(20, 12)).status_code, 409)  # Beyond 14 days.
        self.assertEqual(self.book(at(2, 12), guests=99).status_code, 409)
        self.assertEqual(self.book(at(2, 10)).status_code, 201)
        self.assertIn("2 upcoming", self.book(at(3, 10)).data["detail"])  # The unit's limit for this facility.

    def test_concurrent_bookings(self, _):
        self.bbq.concurrent_bookings = 2
        self.bbq.save()
        self.assertEqual(self.book(at(1, 10)).status_code, 201)
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.book(at(1, 10)).status_code, 201)
        self.assertEqual(self.client.get(f"/v1/facilities/{self.bbq.pk}/availability/",
                                         {"date": at(1, 0).date().isoformat()}).data["slots"][0]["left"], 0)

    def test_scoping_and_cancel(self, _):
        mine = self.book(at(3, 12)).data["booking"]  # Well before the 24-hour cut-off.
        soon = m.Booking.objects.create(condominium=self.condo, facility=self.bbq, unit=self.unit, user=self.alice,
                                        starts_at=timezone.now() + timedelta(hours=2), ends_at=timezone.now() + timedelta(hours=4),
                                        status="confirmed")
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get("/v1/bookings/").data["count"], 0)
        self.assertEqual(self.client.post(f"/v1/bookings/{mine['id']}/cancel/").status_code, 404)
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.post(f"/v1/bookings/{soon.pk}/cancel/").status_code, 409)  # Inside the 24 h cut-off.
        self.assertEqual(self.client.post(f"/v1/bookings/{mine['id']}/cancel/").data["status"], "cancelled")
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get("/v1/bookings/").data["count"], 2)
        self.assertEqual(self.client.post(f"/v1/bookings/{soon.pk}/cancel/").status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"/v1/bookings/{soon.pk}/cancel/", {"reason": "Maintenance"}).data["cancel_reason"], "Maintenance")

    def test_staff_configure_facilities_residents_only_see_active(self, _):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/v1/facilities/", {"condominium": self.condo.pk, "name": "Tennis court", "opens_at": "07:00",
                                                        "closes_at": "22:00", "price_per_slot": "10.00", "open_days": [5, 6],
                                                        "is_active": False}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.post("/v1/facilities/", {"condominium": self.condo.pk, "name": "Bad", "opens_at": "22:00",
                                                              "closes_at": "07:00"}, format="json").status_code, 400)
        self.client.force_authenticate(self.alice)
        self.assertEqual([f["name"] for f in self.client.get("/v1/facilities/").data["results"]], ["BBQ pit"])
        self.assertEqual(self.client.post("/v1/facilities/", {"condominium": self.condo.pk, "name": "X"}, format="json").status_code, 403)


@mock.patch("core.bookings.broadcast")
class PaidBookingTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)
        self.admin = make_staff("admin", self.condo, m.StaffAssignment.Role.ADMIN)
        self.room = m.Facility.objects.create(condominium=self.condo, name="Function room", slot_minutes=60,
                                              price_per_slot=Decimal("25.00"), deposit=Decimal("50.00"))
        self.client.force_authenticate(self.alice)

    def settings(self, **kw):
        return m.PaymentSettings.objects.create(condominium=self.condo, enabled=True, hitpay_api_key="key", hitpay_salt="salt", **kw)

    def book(self, starts_at, slots=1):
        return self.client.post("/v1/bookings/", {"facility": self.room.pk, "starts_at": starts_at.isoformat(), "slots": slots}, format="json")

    def test_needs_payment_settings(self, _):
        response = self.book(at(1, 10))
        self.assertEqual(response.status_code, 409)
        self.assertIn("Online payment is not set up", response.data["detail"])
        self.assertFalse(m.Booking.objects.exists())

    @mock.patch("core.payments.requests.post", return_value=hitpay_response(id="pr_1", url="https://hitpay.test/pay/pr_1"))
    def test_pay_and_confirm(self, post, _):
        self.settings()
        response = self.book(at(1, 10), slots=2)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["payment_url"], "https://hitpay.test/pay/pr_1")
        self.assertTrue(response.data["return_url_prefix"].endswith("/v1/payments/hitpay/return/"))
        booking = m.Booking.objects.get()
        self.assertEqual((booking.status, booking.amount, booking.payment_reference), ("pending_payment", Decimal("100.00"), "pr_1"))
        sent = post.call_args.kwargs["data"]
        self.assertEqual((sent["amount"], sent["currency"], sent["reference_number"]), ("100.00", "SGD", f"booking-{booking.pk}"))
        self.assertIn(f"booking={booking.pk}", sent["redirect_url"])
        self.assertEqual(post.call_args.kwargs["headers"]["X-BUSINESS-API-KEY"], "key")

        # The slot is held while paying.
        slots = self.client.get(f"/v1/facilities/{self.room.pk}/availability/", {"date": at(1, 0).date().isoformat()}).data["slots"]
        self.assertFalse(next(s for s in slots if s["starts_at"].startswith(at(1, 10).date().isoformat() + "T10"))["available"])

        # Neither the redirect's query string nor a forged webhook confirms it: only HitPay's API does.
        with mock.patch("core.payments.requests.get", return_value=hitpay_response(200, status="pending")):
            page = self.client.get(f"/v1/payments/hitpay/return/?booking={booking.pk}&status=completed")
        self.assertContains(page, "Payment processing")
        forged = self.client.post("/v1/payments/hitpay/webhook/", {"payment_request_id": "pr_1", "status": "completed", "hmac": "x"})
        self.assertEqual(forged.status_code, 401)
        # A site that has not entered its salt yet gets no unsigned webhooks acted on either.
        m.PaymentSettings.objects.filter(condominium=self.condo).update(hitpay_salt="")
        with mock.patch("core.payments.requests.get") as get:
            unsigned = self.client.post("/v1/payments/hitpay/webhook/", {"payment_request_id": "pr_1", "status": "completed"})
        self.assertEqual((unsigned.status_code, get.called), (401, False))
        m.PaymentSettings.objects.filter(condominium=self.condo).update(hitpay_salt="salt")

        fields = {"payment_id": "p_9", "payment_request_id": "pr_1", "status": "completed", "reference_number": f"booking-{booking.pk}"}
        message = "".join(f"{k}{fields[k]}" for k in sorted(fields))
        signed = {**fields, "hmac": hmac.new(b"salt", message.encode(), hashlib.sha256).hexdigest()}
        with mock.patch("core.payments.requests.get", return_value=hitpay_response(200, status="completed")) as get:
            self.assertEqual(self.client.post("/v1/payments/hitpay/webhook/", signed).status_code, 200)
        self.assertIn("/payment-requests/pr_1", get.call_args.args[0])
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.payment_status), ("confirmed", "paid"))
        self.assertIsNotNone(booking.paid_at)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"/v1/bookings/{booking.pk}/cancel/").data["payment_status"], "paid")
        self.assertEqual(self.client.post(f"/v1/bookings/{booking.pk}/refunded/").data["payment_status"], "refunded")

    @mock.patch("core.payments.requests.post", return_value=hitpay_response(id="pr_2", url="https://hitpay.test/pay/pr_2"))
    def test_unpaid_bookings_release_their_slots(self, post, _):
        self.settings(sandbox=True)
        self.book(at(1, 10))
        self.assertIn("sandbox", post.call_args.args[0])
        booking = m.Booking.objects.get()
        m.Booking.objects.filter(pk=booking.pk).update(payment_expires_at=timezone.now() - timedelta(minutes=1))
        with mock.patch("core.payments.requests.get", return_value=hitpay_response(200, status="pending")):
            self.assertEqual(bookings.expire_stale(), 1)
        booking.refresh_from_db()
        self.assertEqual(booking.status, "expired")
        self.assertEqual(self.book(at(1, 10)).status_code, 201)  # The slot is free again.
        # The first one is paid late, but the slot is taken: it is cancelled with a refund due.
        with mock.patch("core.payments.requests.get", return_value=hitpay_response(200, status="completed")):
            m.Booking.objects.filter(pk=booking.pk).update(payment_status="pending")
            late = bookings.refresh_payment(booking)
        self.assertEqual((late.status, late.payment_status), ("cancelled", "paid"))
        self.assertIn("refund due", late.cancel_reason)

    @mock.patch("core.payments.requests.post", return_value=hitpay_response(422, message="bad key"))
    def test_hitpay_refusal_releases_the_slot(self, post, _):
        self.settings()
        self.assertEqual(self.book(at(1, 10)).status_code, 502)
        self.assertEqual(m.Booking.objects.get().status, "expired")

    def test_payment_settings_are_admin_only_and_secret(self, _):
        self.settings()
        self.assertEqual(self.client.get(f"/v1/payment-settings/?condominium={self.condo.pk}").status_code, 403)
        self.client.force_authenticate(self.admin)
        data = self.client.get(f"/v1/payment-settings/?condominium={self.condo.pk}").data
        self.assertNotIn("hitpay_api_key", data)
        self.assertTrue(data["has_hitpay_api_key"])
        self.assertTrue(data["webhook_url"].endswith("/v1/payments/hitpay/webhook/"))
        self.client.patch(f"/v1/payment-settings/?condominium={self.condo.pk}", {"hitpay_api_key": "", "sandbox": False}, format="json")
        settings = m.PaymentSettings.objects.get()
        self.assertEqual((settings.hitpay_api_key, settings.sandbox), ("key", False))  # Blank keeps the secret.


class FeedbackTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)
        self.bob = make_resident("bob", make_unit(self.condo, floor="09", number="09"))
        self.admin = make_staff("admin", self.condo, m.StaffAssignment.Role.ADMIN)
        self.guard = make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY)

    def test_rate_reply_and_summary(self):
        self.client.force_authenticate(self.alice)
        response = self.client.post("/v1/feedback/", {"rating": 4, "category": "security", "comment": "Friendly guards"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.post("/v1/feedback/", {"rating": 6}, format="json").status_code, 400)
        self.client.force_authenticate(self.bob)
        self.client.post("/v1/feedback/", {"rating": 2, "category": "cleanliness"}, format="json")
        self.assertEqual(self.client.get("/v1/feedback/").data["count"], 1)  # Only his own.

        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.post(f"/v1/feedback/{response.data['id']}/reply/", {"reply": "Thanks"}).status_code, 403)
        self.client.force_authenticate(self.admin)
        replied = self.client.post(f"/v1/feedback/{response.data['id']}/reply/", {"reply": "Thank you!"}, format="json").data
        self.assertEqual((replied["status"], replied["replied_by_name"]), ("in_progress", "admin"))
        summary = self.client.get(f"/v1/feedback/summary/?condominium={self.condo.pk}").data
        self.assertEqual((summary["count"], summary["average"], summary["by_rating"]["4"], summary["open"]), (2, 3.0, 1, 2))

        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.get(f"/v1/feedback/{response.data['id']}/").data["reply"], "Thank you!")

    def test_new_feedback_is_sent_to_the_guardhouse(self):
        self.client.force_authenticate(self.alice)
        with mock.patch("core.amenity_views.broadcast") as broadcast:
            response = self.client.post("/v1/feedback/", {"rating": 1, "category": "security"}, format="json")
        broadcast.assert_called_once_with(self.condo.pk, None, "feedback", response.data)

    def test_staff_cannot_post_feedback(self):
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.post("/v1/feedback/", {"rating": 5}, format="json").status_code, 403)


@mock.patch("core.tasks.open_gate.delay")
class RemoteOpenTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main gate")
        self.client.force_authenticate(self.alice)

    def test_only_enabled_gates_and_residents(self, open_gate):
        url = f"/v1/gates/{self.gate.pk}/remote_open/"
        self.assertEqual(self.client.post(url).status_code, 403)
        self.gate.resident_remote_open = True
        self.gate.save()
        self.assertTrue(self.client.get("/v1/gates/").data["results"][0]["resident_remote_open"])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 202)
        log = m.AccessLog.objects.get()
        self.assertEqual((log.method, log.actor, log.unit, log.result), ("app", self.alice, self.unit, "granted"))
        self.client.force_authenticate(make_resident("stranger", make_unit(make_condo("beta"))))
        self.assertEqual(self.client.post(url).status_code, 404)


@mock.patch("core.parking.broadcast")
@mock.patch("core.payments.requests.post", return_value=hitpay_response(id="pr_p", url="https://hitpay.test/pay/pr_p"))
class SeasonParkingTests(APITestCase):
    def setUp(self):
        self.condo = make_condo(season_parking_enabled=True, season_parking_fee=Decimal("80.00"), season_parking_quota=1)
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)
        m.PaymentSettings.objects.create(condominium=self.condo, enabled=True, hitpay_api_key="key", hitpay_salt="salt")
        self.client.force_authenticate(self.alice)

    def buy(self, plate="SKT 8821 M", months=3, **extra):
        return self.client.post("/v1/parking-permits/", {"unit": self.unit.pk, "plate_number": plate, "months": months,
                                                          "holder_name": "Mr Lim", **extra}, format="json")

    def paid(self, permit_id):
        with mock.patch("core.payments.requests.get", return_value=hitpay_response(200, status="completed")):
            return self.client.post(f"/v1/parking-permits/{permit_id}/refresh/").data

    def test_buy_pay_and_renew(self, post, _):
        offer = self.client.get("/v1/parking-permits/offer/", {"condominium": self.condo.pk}).data
        self.assertEqual((offer["enabled"], offer["monthly_fee"], offer["lots_left"]), (True, "80.00", 1))
        response = self.buy()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["payment_url"], "https://hitpay.test/pay/pr_p")
        permit = response.data["permit"]
        self.assertEqual((permit["amount"], permit["plate_number"], permit["status"]), ("240.00", "SKT8821M", "pending_payment"))
        self.assertEqual(post.call_args.kwargs["data"]["reference_number"], f"parking-{permit['id']}")
        self.assertFalse(m.Vehicle.objects.exists())  # Nothing parks before it is paid.

        done = self.paid(permit["id"])
        self.assertEqual(done["status"], "paid")
        vehicle = m.Vehicle.objects.get()
        today = timezone.localdate()
        self.assertEqual((vehicle.kind, vehicle.holder_name, vehicle.valid_from), ("season", "Mr Lim", today))
        self.assertEqual(vehicle.valid_until.isoformat(), done["ends_on"])
        self.assertTrue(vehicle.valid_on(today))

        # Renewing carries on from the day after the current pass ends, and needs no new lot.
        renewal = self.buy(months=1).data["permit"]
        self.assertEqual(renewal["starts_on"], (vehicle.valid_until + timedelta(days=1)).isoformat())
        self.paid(renewal["id"])
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.valid_until.isoformat(), renewal["ends_on"])
        self.assertEqual(vehicle.valid_from, today)

    def test_rules(self, post, _):
        self.assertEqual(self.buy(months=2).status_code, 409)  # 1, 3, 6 or 12 months only.
        m.Vehicle.objects.create(unit=self.unit, plate_number="SBA1A")
        self.assertIn("resident's car", self.buy(plate="SBA1A").data["detail"])
        self.paid(self.buy().data["permit"]["id"])
        self.assertIn("lots are taken", self.buy(plate="SGX2B").data["detail"])  # Quota of 1.
        # Another unit's resident cannot buy for this unit.
        other = make_resident("bob", make_unit(self.condo, "02", "02"))
        self.client.force_authenticate(other)
        self.assertEqual(self.buy(plate="SGX3C").status_code, 403)
        self.condo.season_parking_enabled = False
        self.condo.save()
        self.assertFalse(self.client.get("/v1/parking-permits/offer/", {"condominium": self.condo.pk}).data["enabled"])

    def test_needs_the_facilities_module(self, post, _):
        set_plan(self.condo, "standard", disabled_modules=["facilities"])
        self.assertFalse(self.client.get("/v1/parking-permits/offer/", {"condominium": self.condo.pk}).data["enabled"])
        self.assertIn("not sold online", self.buy().data["detail"])

    def test_return_page_and_webhook(self, post, _):
        permit = self.buy().data["permit"]
        with mock.patch("core.payments.requests.get", return_value=hitpay_response(200, status="completed")):
            page = self.client.get(f"/v1/payments/hitpay/return/?permit={permit['id']}")
        self.assertContains(page, "Season parking paid")
        fields = {"payment_request_id": "pr_x", "status": "completed", "reference_number": f"parking-{permit['id']}"}
        message = "".join(f"{k}{fields[k]}" for k in sorted(fields))
        signed = {**fields, "hmac": hmac.new(b"salt", message.encode(), hashlib.sha256).hexdigest()}
        self.assertEqual(self.client.post("/v1/payments/hitpay/webhook/", signed).status_code, 200)


@mock.patch("core.tasks.open_gate.delay")
@mock.patch("core.bookings.broadcast")
class FacilityCheckInTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)
        self.door = m.AccessGate.objects.create(condominium=self.condo, name="Function room door")
        self.room = m.Facility.objects.create(condominium=self.condo, name="Function room", opens_at=time(0), closes_at=time(23, 59),
                                              slot_minutes=60, max_slots_per_booking=2, gate=self.door)
        kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby kiosk")
        self.token = kiosk.issue_token()
        kiosk.save()

    def booking(self, starts_in, status="confirmed"):
        start = timezone.now().replace(second=0, microsecond=0) + starts_in
        return m.Booking.objects.create(condominium=self.condo, facility=self.room, unit=self.unit, user=self.alice,
                                        starts_at=start, ends_at=start + timedelta(hours=1), status=status)

    def scan(self, code):
        return self.client.post("/v1/kiosk/facilities/checkin/", {"code": code}, format="json", HTTP_AUTHORIZATION=f"Kiosk {self.token}")

    def test_check_in_opens_the_door_within_the_booking(self, _, open_gate):
        now_ = self.booking(timedelta(minutes=10))  # Starts in 10 minutes: 15 minutes early is fine.
        response = self.scan(now_.qr_payload)
        self.assertEqual((response.data["result"], response.data["door_opened"], response.data["facility"]), ("granted", True, "Function room"))
        now_.refresh_from_db()
        self.assertIsNotNone(now_.checked_in_at)
        log = m.AccessLog.objects.get()
        self.assertEqual((log.method, log.gate, log.unit), ("booking", self.door, self.unit))

        later = self.booking(timedelta(hours=3))
        self.assertIn("Too early", self.scan(later.qr_payload).data["reason"])
        gone = self.booking(-timedelta(hours=2))
        self.assertEqual(self.scan(gone.qr_payload).data["reason"], "This booking has ended.")
        cancelled = self.booking(timedelta(minutes=5), status="cancelled")
        self.assertEqual(self.scan(cancelled.qr_payload).data["reason"], "This booking is cancelled.")
        self.assertEqual(self.scan("ELIX-WALKIN:abc").data["result"], "denied")
        self.assertEqual(m.AccessLog.objects.filter(result="denied").count(), 3)  # Denials at the door are logged too.

    def test_schedule_and_resident_qr(self, *_):
        self.booking(timedelta(minutes=-10))
        rows = self.client.get("/v1/kiosk/facilities/", HTTP_AUTHORIZATION=f"Kiosk {self.token}").data
        self.assertEqual(rows[0]["name"], "Function room")
        current = next(slot for slot in rows[0]["slots"] if slot["now"])
        self.assertTrue(current["booked"])
        self.assertNotIn("unit", rows[0]["slots"][0])  # Nobody's unit is shown in the lobby.
        self.client.force_authenticate(self.alice)
        booking = m.Booking.objects.get()
        response = self.client.get(f"/v1/bookings/{booking.pk}/qr/")
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "image/png"))


@mock.patch("core.bookings.broadcast")
class NoShowTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)
        self.room = m.Facility.objects.create(condominium=self.condo, name="Function room", opens_at=time(0), closes_at=time(23, 59),
                                              slot_minutes=60, no_show_minutes=15)

    def booking(self, started_ago):
        start = timezone.now() - started_ago
        return m.Booking.objects.create(condominium=self.condo, facility=self.room, unit=self.unit, user=self.alice,
                                        starts_at=start, ends_at=start + timedelta(hours=1), status="confirmed")

    def test_flags_late_bookings_only_where_on(self, _):
        late = self.booking(timedelta(minutes=20))
        early = self.booking(timedelta(minutes=5))
        came = self.booking(timedelta(minutes=30))
        m.Booking.objects.filter(pk=came.pk).update(checked_in_at=timezone.now())
        self.assertEqual(bookings.mark_no_shows(), 1)
        late.refresh_from_db()
        self.assertIsNotNone(late.no_show_at)
        self.assertEqual(late.status, "confirmed")  # Kept: the facility does not release no-shows.
        self.assertEqual(bookings.mark_no_shows(), 0)  # Once only.
        # Coming late still checks in, and is no longer a no-show.
        booking, problem = bookings.check_in(self.condo.pk, late.qr_payload)
        self.assertEqual(problem, "")
        late.refresh_from_db()
        self.assertIsNone(late.no_show_at)

        self.room.no_show_minutes = 0  # Off: nothing is flagged.
        self.room.save()
        self.booking(timedelta(minutes=40))
        self.assertEqual(bookings.mark_no_shows(), 0)
        self.assertIsNone(m.Booking.objects.get(pk=early.pk).no_show_at)

    def test_release_and_resident_notice(self, _):
        self.room.release_no_shows = True
        self.room.save()
        late = self.booking(timedelta(minutes=20))
        bookings.mark_no_shows()
        late.refresh_from_db()
        self.assertEqual(late.status, "cancelled")
        self.assertIn("No-show", late.cancel_reason)
        self.assertEqual(bookings.check_in(self.condo.pk, late.qr_payload)[1], "This booking is cancelled.")
        self.client.force_authenticate(self.alice)
        kinds = [n["kind"] for n in self.client.get("/v1/notifications/").data["results"]]
        self.assertIn("booking_no_show", kinds)
        self.assertNotIn("booking_cancelled", kinds)  # One notice, not two.
        admin = make_staff("admin", self.condo, m.StaffAssignment.Role.ADMIN)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/v1/bookings/", {"condominium": self.condo.pk, "no_show": 1}).data["count"], 1)


@mock.patch("core.visits.broadcast")
@mock.patch("core.tasks.open_gate.delay")
@mock.patch("core.bookings.broadcast")
class BookingGuestTests(APITestCase):
    def setUp(self):
        self.condo = make_condo(lpr_enabled=True)
        self.unit = make_unit(self.condo)
        self.alice = make_resident("alice", self.unit)
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main gate")
        self.bbq = m.Facility.objects.create(condominium=self.condo, name="BBQ pit", opens_at=time(0), closes_at=time(23, 59),
                                             slot_minutes=60, capacity=10)
        start = timezone.now().replace(second=0, microsecond=0) + timedelta(minutes=20)
        self.booking = m.Booking.objects.create(condominium=self.condo, facility=self.bbq, unit=self.unit, user=self.alice,
                                                starts_at=start, ends_at=start + timedelta(hours=2), guests=3, status="confirmed")
        self.client.force_authenticate(self.alice)

    def invite(self, plates=()):
        return self.client.post(f"/v1/bookings/{self.booking.pk}/guests/", {"plates": list(plates)}, format="json")

    def test_one_qr_for_the_guests_and_cars_for_the_barrier(self, *_):
        self.assertEqual(self.client.get(f"/v1/bookings/{self.booking.pk}/guests/").status_code, 404)
        data = self.invite(["sgx 1 a", "SGX1A"]).data
        self.assertEqual((data["entries"], data["plates"]), (3, ["SGX1A"]))
        shared = m.Invitation.objects.get(pk=data["invitation"])
        self.assertEqual((shared.booking, shared.valid_from, shared.valid_until),
                         (self.booking, self.booking.starts_at - timedelta(minutes=30), self.booking.ends_at))
        # Inviting again keeps the shared QR and replaces the cars.
        again = self.invite(["SBA2B"]).data
        self.assertEqual((again["invitation"], again["plates"]), (shared.pk, ["SBA2B"]))
        self.assertEqual(m.Invitation.objects.get(vehicle_plate="SGX1A").status, "cancelled")

        # A guest scans the shared QR at the kiosk: welcomed to the facility, and overstays when the booking ends.
        kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby", gate=self.gate)
        token = kiosk.issue_token()
        kiosk.save()
        self.client.force_authenticate(None)
        response = self.client.post("/v1/kiosk/checkin/", {"code": shared.share_url}, format="json", HTTP_AUTHORIZATION=f"Kiosk {token}")
        self.assertEqual(response.data["result"], "granted", response.data)
        self.assertEqual(response.data["invitation"]["facility"], "BBQ pit")
        visit = m.Visit.objects.get()
        self.assertEqual(visits.overstay_at(visit), self.booking.ends_at)
        self.client.force_authenticate(make_staff("guard", self.condo, m.StaffAssignment.Role.SECURITY))
        listed = self.client.get("/v1/visits/", {"condominium": self.condo.pk, "state": "on_site"}).data["results"][0]
        self.assertEqual(listed["facility"], "BBQ pit")

    def test_rules_and_cancelling_the_booking(self, *_):
        self.assertIn("At most 5", self.invite([f"SGX{i}A" for i in range(6)]).data["detail"])
        self.invite(["SGX1A"])
        bob = make_resident("bob", make_unit(self.condo, "07", "01"))
        self.client.force_authenticate(bob)
        self.assertEqual(self.invite().status_code, 404)  # Another unit's booking.
        self.client.force_authenticate(make_staff("admin", self.condo, m.StaffAssignment.Role.ADMIN))
        self.assertEqual(self.client.post(f"/v1/bookings/{self.booking.pk}/cancel/").status_code, 200)
        self.client.force_authenticate(self.alice)
        self.assertFalse(m.Invitation.objects.filter(status="active").exists())
        self.assertIn("confirmed booking", self.invite().data["detail"])
