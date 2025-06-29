from django.urls import path
from . import views

urlpatterns = [
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
    path('api/run-benchmark/', views.api_run_benchmark, name='api_run_benchmark'),
]
