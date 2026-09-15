from django.urls import path
from .views import classify_view

urlpatterns = [
    path('', classify_view, name='classify'),
]

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    ...
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
