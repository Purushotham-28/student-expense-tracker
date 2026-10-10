from django.urls import path, re_path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    health_check,
    register_user,
    login_user,
    user_profile_view,
    upload_statement,
    list_statements,
    statement_detail,
    categorize_statement_view,
    payee_mappings_view,
    categorize_transaction_view,
)

urlpatterns = [
    path('health/', health_check, name='health_check'),

    # Auth
    re_path(r'^auth/register/?$', register_user, name='auth_register'),
    re_path(r'^auth/login/?$', login_user, name='auth_login'),
    re_path(r'^auth/token/refresh/?$', TokenRefreshView.as_view(), name='token_refresh'),

    # Profile
    re_path(r'^profile/?$', user_profile_view, name='user_profile'),

    # Statements
    re_path(r'^statements/upload/?$', upload_statement, name='statement_upload'),
    re_path(r'^statements/?$', list_statements, name='statement_list'),
    re_path(r'^statements/(?P<pk>\d+)/?$', statement_detail, name='statement_detail'),
    re_path(r'^statements/(?P<pk>\d+)/categorize/?$', categorize_statement_view, name='statement_categorize'),

    # Payee Mappings & Categorization
    re_path(r'^payee-mappings/?$', payee_mappings_view, name='payee_mappings'),
    re_path(r'^transactions/(?P<pk>\d+)/categorize/?$', categorize_transaction_view, name='transaction_categorize'),
]
