from django.urls import path
from . import views

urlpatterns = [
    # Landing page
    path('', views.company_selection, name='company_selection'),
    
    # Company-specific routes
    path('<str:company_size>/', views.schedule_dashboard, name='schedule_dashboard'),
    path('<str:company_size>/month/', views.month_view, name='month_view'),
    path('<str:company_size>/day/<str:date>/', views.day_view, name='day_view'),
    path('<str:company_size>/employee/<int:employee_id>/', views.employee_view, name='employee_view'),
    path('<str:company_size>/analytics/', views.analytics_view, name='analytics_view'),
    
    # API endpoints for AJAX
    path('api/<str:company_size>/schedule/<str:year>/<str:month>/', views.api_schedule_data, name='api_schedule_data'),
]
