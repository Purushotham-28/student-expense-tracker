from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def root_api_index(request):
    return JsonResponse({
        'message': 'Student Expense Tracker - Django REST Backend API',
        'status': 'online',
        'frontend_url': 'http://localhost:5173',
        'endpoints': {
            'health': '/api/health/',
            'admin': '/admin/',
        }
    })

urlpatterns = [
    path('', root_api_index, name='root_index'),
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
]
