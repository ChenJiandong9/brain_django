"""
ASGI config for brain_django project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path
from brain_start.consumers import EEGDataConsumer


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'brain_django.settings')

 
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter([
        re_path(r'^ws/eeg/$', EEGDataConsumer.as_asgi()),
    ]),
})
 