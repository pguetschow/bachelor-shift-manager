from django.urls import path
from . import views

urlpatterns = [
    path('schedule/', views.schedule_view, name='schedule'),
]
