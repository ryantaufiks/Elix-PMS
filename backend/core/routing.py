from django.urls import path

from .realtime import EventsConsumer

websocket_urlpatterns = [
    path("ws/events/", EventsConsumer.as_asgi()),
]
