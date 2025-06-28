from django.urls import path
from . import views

urlpatterns = [
    # Landing page
    path('', views.company_selection, name='company_selection'),
    
    # Company-specific routes
    path('<int:company_id>/', views.schedule_dashboard, name='schedule_dashboard'),
    path('<int:company_id>/month/', views.month_view, name='month_view'),
    path('<int:company_id>/day/<str:date>/', views.day_view, name='day_view'),
    path('<int:company_id>/employee/<int:employee_id>/', views.employee_view, name='employee_view'),
    path('<int:company_id>/analytics/', views.analytics_view, name='analytics_view'),
    
    # API endpoints for AJAX
    path('api/<int:company_id>/schedule/<str:year>/<str:month>/', views.api_schedule_data, name='api_schedule_data'),
]
