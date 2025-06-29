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
]
