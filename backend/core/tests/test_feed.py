from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from core import models as m
from core import visits

from .factories import make_condo, make_resident, make_staff, make_unit

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


class NotificationTests(APITestCase):
    def setUp(self):
        self.condo = make_condo()
        self.unit = make_unit(self.condo)
        self.resident = make_resident("res", self.unit)
        self.neighbour = make_resident("nb", make_unit(self.condo, number="99"))
        self.gate = m.AccessGate.objects.create(condominium=self.condo, name="Main gate")

    def feed(self, user=None, **params):
        self.client.force_authenticate(user or self.resident)
        return self.client.get("/v1/notifications/", params).data

    def test_one_notification_per_event_newest_first(self):
        visit = visits.create(self.condo.pk, unit=self.unit, purpose="guest", name="Tan", source="staff")
        visits.check_out(visit)
        m.AccessLog.objects.create(condominium=self.condo, gate=self.gate, unit=self.unit, method="lpr",
                                   result="granted", plate_number="SGX1234A")
        call = m.IntercomCall.objects.create(condominium=self.condo, unit=self.unit, status="missed", visitor_name="Lim")
        # The gate opening that answered the call is the call's story, not a second notification.
        m.AccessLog.objects.create(condominium=self.condo, gate=self.gate, unit=self.unit, method="intercom",
                                   result="granted", intercom_call=call)
        data = self.feed()
        kinds = [n["kind"] for n in data["results"]]
        self.assertEqual(data["count"], 4)
        self.assertEqual(sorted(kinds), ["call_missed", "gate_open", "visit_in", "visit_out"])
        self.assertEqual(data["results"][0]["at"] >= data["results"][-1]["at"], True)
        self.assertEqual(self.feed(self.neighbour)["count"], 0)  # Only one's own units.

    def test_pages(self):
        for i in range(5):
            m.AccessLog.objects.create(condominium=self.condo, gate=self.gate, unit=self.unit, method="app", result="granted")
        first, second = self.feed(page=1, page_size=3), self.feed(page=2, page_size=3)
        self.assertEqual((first["count"], len(first["results"]), len(second["results"])), (5, 3, 2))
        self.assertFalse({n["id"] for n in first["results"]} & {n["id"] for n in second["results"]})

    def test_feedback_reply(self):
        m.Feedback.objects.create(condominium=self.condo, unit=self.unit, user=self.resident, rating=4, category="security",
                                  reply="Thanks!", replied_at="2026-11-08T10:00:00+08:00")
        self.assertIn("feedback_reply", [n["kind"] for n in self.feed()["results"]])


READINGS = {
    "air-temperature": {"stations": [{"id": "S1", "name": "Near", "location": {"latitude": 1.30, "longitude": 103.85}},
                                     {"id": "S2", "name": "Far", "location": {"latitude": 1.45, "longitude": 103.70}}],
                        "readings": [{"timestamp": "2026-11-08T22:53:00+08:00", "data": [{"stationId": "S1", "value": 28.4},
                                                                                         {"stationId": "S2", "value": 25.0}]}]},
    "relative-humidity": {"stations": [{"id": "S1", "name": "Near", "location": {"latitude": 1.30, "longitude": 103.85}}],
                          "readings": [{"timestamp": "2026-11-08T22:53:00+08:00", "data": [{"stationId": "S1", "value": 80.0}]}]},
    "two-hr-forecast": {"area_metadata": [{"name": "City", "label_location": {"latitude": 1.29, "longitude": 103.85}},
                                          {"name": "Woodlands", "label_location": {"latitude": 1.43, "longitude": 103.78}}],
                        "items": [{"valid_period": {"text": "10.30 pm to 12.30 am"},
                                   "forecasts": [{"area": "City", "forecast": "Light Rain"}, {"area": "Woodlands", "forecast": "Fair"}]}]},
}


def fake_get(url, params=None, headers=None, timeout=None):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    if "onemap" in url:
        response.json.return_value = {"results": [{"LATITUDE": "1.2999", "LONGITUDE": "103.8451"}]}
    else:
        response.json.return_value = {"code": 0, "data": READINGS[url.rsplit("/", 1)[1]]}
    return response


@override_settings(CACHES=LOCMEM)
@mock.patch("core.weather.requests.get", side_effect=fake_get)
class WeatherTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.condo = make_condo(postal_code="238839")
        self.resident = make_resident("res", make_unit(self.condo))

    def test_nearest_station_and_area(self, get):
        self.client.force_authenticate(self.resident)
        data = self.client.get(f"/v1/weather/?condominium={self.condo.pk}").data
        self.assertEqual((data["temperature"], data["humidity"], data["forecast"], data["area"]), (28.4, 80.0, "Light Rain", "City"))
        self.client.get(f"/v1/weather/?condominium={self.condo.pk}")
        self.assertEqual(get.call_count, 4)  # OneMap once, three datasets once: the rest is cached.

    def test_other_sites_cannot_ask(self, _):
        self.client.force_authenticate(make_staff("guard", make_condo("other"), m.StaffAssignment.Role.SECURITY))
        self.assertEqual(self.client.get(f"/v1/weather/?condominium={self.condo.pk}").status_code, 403)

    def test_kiosk_and_outage(self, get):
        kiosk = m.Kiosk.objects.create(condominium=self.condo, name="Lobby")
        token = kiosk.issue_token()
        kiosk.save()
        self.client.credentials(HTTP_AUTHORIZATION=f"Kiosk {token}")
        self.assertEqual(self.client.get("/v1/kiosk/weather/").data["temperature"], 28.4)
        cache.clear()
        get.side_effect = __import__("requests").ConnectionError()
        self.assertEqual(self.client.get("/v1/kiosk/weather/").status_code, 503)
