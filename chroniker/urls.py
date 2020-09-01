from django.urls import path
from chroniker import views

urlpatterns = [
    path('', views.jobs, name='jobs'),
    path('<int:pk>', views.job, name='job'),
    path('<int:pk>/run', views.job, {'run': True}, name='job_run'),
    path('<int:pk>/last_run', views.job, {'last_run': True}, name='job_last_run'),
    path('<int:pk>/toggle', views.job, {'toggle': True}, name='job_toggle'),
    path('log/<int:pk>', views.log, name='job_log'),
]
