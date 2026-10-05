from django.urls import path, re_path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import health_check, register_user, login_user, user_profile_view

urlpatterns = [
    path('health/', health_check, name='health_check'),
    re_path(r'^auth/register/?$', register_user, name='auth_register'),
    re_path(r'^auth/login/?$', login_user, name='auth_login'),
    re_path(r'^auth/token/refresh/?$', TokenRefreshView.as_view(), name='token_refresh'),
    re_path(r'^profile/?$', user_profile_view, name='user_profile'),
]
