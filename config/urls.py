from django.contrib import admin
from django.urls import path, include
from django.conf import settings             # <-- ADICIONE ESTA LINHA
from django.conf.urls.static import static   # <-- ADICIONE ESTA LINHA
from gestao.views import SGDPPasswordResetView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('gestao.urls')),
    path('accounts/password_reset/', SGDPPasswordResetView.as_view(), name='password_reset'),
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)