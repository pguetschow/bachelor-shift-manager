from django.urls import path, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from . import views

urlpatterns = [
    # Serve Vue.js frontend at root
    path('', views.serve_vue_app, name='serve_vue_app'),
    
    # Serve Vue.js assets from /assets/ path
    path('assets/<path:path>', serve, {
        'document_root': settings.BASE_DIR / 'dist' / 'assets',
        'show_indexes': False,
    }, name='vue_assets'),
    
    # API endpoints for Vue.js frontend
    path('api/companies/', views.api_companies, name='api_companies'),
    path('api/companies/<int:company_id>/', views.api_company_detail, name='api_company_detail'),
    path('api/companies/<int:company_id>/algorithms/', views.api_company_algorithms, name='api_company_algorithms'),
    path('api/companies/<int:company_id>/schedule/', views.api_company_schedule, name='api_company_schedule'),
    path('api/companies/<int:company_id>/employees/', views.api_company_employees, name='api_company_employees'),
    path('api/companies/<int:company_id>/shifts/', views.api_company_shifts, name='api_company_shifts'),
    path('api/companies/<int:company_id>/day/<str:date>/', views.api_company_day_schedule, name='api_company_day_schedule'),
    path('api/companies/<int:company_id>/employees/<int:employee_id>/schedule/', views.api_company_employee_schedule, name='api_company_employee_schedule'),
    path('api/companies/<int:company_id>/employees/<int:employee_id>/yearly/', views.api_company_employee_yearly_schedule, name='api_company_employee_yearly_schedule'),
    path('api/companies/<int:company_id>/employee-statistics/', views.api_company_employee_statistics, name='api_company_employee_statistics'),
    path('api/load-fixtures/', views.api_load_fixtures, name='api_load_fixtures'),
    path('api/upload-status/', views.api_upload_status, name='api_upload_status'),
    path('api/companies/<int:company_id>/analytics/', views.api_company_analytics, name='api_company_analytics'),
    
    # Catch-all route for Vue.js routes - must be last
    re_path(r'^(?!api/|admin/|assets/|static/).*$', views.serve_vue_app, name='vue_catch_all'),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static('/static/', document_root=settings.BASE_DIR / 'dist')
