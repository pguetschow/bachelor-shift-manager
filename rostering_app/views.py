from django.shortcuts import render
from rostering_app.models import ScheduleEntry

def schedule_view(request):
    entries = ScheduleEntry.objects.filter(archived=False).order_by('date')
    context = {'entries': entries}
    return render(request, 'rostering_app/schedule.html', context)