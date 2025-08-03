from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('rostering_app.urls')),
]

# Serve static files
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # In production, we still need to serve static files
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Serve Vue.js assets in production
if not settings.DEBUG:
    urlpatterns += [
        path('assets/<path:path>', serve, {
            'document_root': settings.BASE_DIR / 'dist' / 'assets',
            'show_indexes': False,
        }, name='vue_assets_prod'),
    ]
