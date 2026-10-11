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
    list_transactions_view,
    confirm_transaction_view,
    runway_view,
    whatif_view,
    goals_view,
    goal_detail_view,
    goal_contribute_view,
    goal_suggestion_view,
    health_score_view,
    chat_view,
    chat_history_view,
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
    re_path(r'^transactions/?$', list_transactions_view, name='transaction_list'),
    re_path(r'^transactions/(?P<pk>\d+)/categorize/?$', categorize_transaction_view, name='transaction_categorize'),
    re_path(r'^transactions/(?P<pk>\d+)/confirm/?$', confirm_transaction_view, name='transaction_confirm'),

    # Phase 5 & 7 — Forecasting, Runway Simulator & Health Score
    re_path(r'^planning/runway/?$', runway_view, name='planning_runway'),
    re_path(r'^planning/whatif/?$', whatif_view, name='planning_whatif'),
    re_path(r'^planning/health-score/?$', health_score_view, name='planning_health_score'),

    # Phase 6 — Goal Planner & Adaptive Savings
    re_path(r'^goals/?$', goals_view, name='goals_list_create'),
    re_path(r'^goals/suggestion/?$', goal_suggestion_view, name='goal_suggestion'),
    re_path(r'^goals/(?P<pk>\d+)/?$', goal_detail_view, name='goal_detail'),
    re_path(r'^goals/(?P<pk>\d+)/contribute/?$', goal_contribute_view, name='goal_contribute'),
    re_path(r'^goals/(?P<pk>\d+)/suggestion/?$', goal_suggestion_view, name='goal_specific_suggestion'),

    # Phase 8 — AI Chatbox (Claude API with Function Calling)
    re_path(r'^chat/?$', chat_view, name='chat'),
    re_path(r'^chat/history/?$', chat_history_view, name='chat_history'),
]
