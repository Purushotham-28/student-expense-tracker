"""
Phase 1 Backend Tests — Auth, Profile & Monthly Budget Limit
Covers: registration, login, JWT profile access, budget update, and edge cases.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from .models import UserProfile


class AuthAndProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = '/api/auth/register/'
        self.login_url = '/api/auth/login/'
        self.profile_url = '/api/profile/'
        self.refresh_url = '/api/auth/token/refresh/'

        self.student_data = {
            'username': 'rahul_sharma',
            'email': 'rahul@campus.edu',
            'password': 'SecurePassword123!',
            'college_roll_number': 'CS-2026-042',
            'monthly_income': '1000.00',
            'monthly_budget_limit': '500.00',
        }

    # ------------------------------------------------------------------ #
    # Test 1 — Successful registration returns JWT tokens & correct profile
    # ------------------------------------------------------------------ #
    def test_student_registration_success(self):
        """
        POST /api/auth/register
        A new student can register with a unique roll number.
        The response must include JWT access/refresh tokens, a profile
        object with the correct roll number, budget limit, and the
        is_onboarded flag must be True because budget_limit > 0.
        """
        response = self.client.post(self.register_url, self.student_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertIn('profile', response.data)
        self.assertEqual(response.data['profile']['college_roll_number'], 'CS-2026-042')
        self.assertEqual(float(response.data['profile']['monthly_budget_limit']), 500.00)
        # is_onboarded must be True when budget limit > 0
        self.assertTrue(response.data['profile']['is_onboarded'])

        # Verify records created in the database
        self.assertTrue(User.objects.filter(username='rahul_sharma').exists())
        profile = UserProfile.objects.get(college_roll_number='CS-2026-042')
        self.assertEqual(float(profile.monthly_income), 1000.00)

    # ------------------------------------------------------------------ #
    # Test 2 — Duplicate roll number, duplicate username/email are rejected
    # ------------------------------------------------------------------ #
    def test_duplicate_roll_number_and_username_registration_fails(self):
        """
        POST /api/auth/register (duplicate attempts)
        Registering with the same college roll number must return 400.
        Registering with the same username must also return 400.
        Registering with the same email must also return 400.
        """
        # First registration succeeds
        self.client.post(self.register_url, self.student_data, format='json')

        # Duplicate roll number
        duplicate_roll = {
            'username': 'amit_verma',
            'email': 'amit@campus.edu',
            'password': 'AnotherPassword123!',
            'college_roll_number': 'CS-2026-042',  # same roll
        }
        resp = self.client.post(self.register_url, duplicate_roll, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('college_roll_number', resp.data.get('details', {}))

        # Duplicate username
        duplicate_username = {
            'username': 'rahul_sharma',  # same username
            'email': 'other@campus.edu',
            'password': 'AnotherPassword123!',
            'college_roll_number': 'CS-2026-999',
        }
        resp2 = self.client.post(self.register_url, duplicate_username, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', resp2.data.get('details', {}))

        # Duplicate email
        duplicate_email = {
            'username': 'new_user',
            'email': 'rahul@campus.edu',  # same email
            'password': 'AnotherPassword123!',
            'college_roll_number': 'CS-2026-888',
        }
        resp3 = self.client.post(self.register_url, duplicate_email, format='json')
        self.assertEqual(resp3.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', resp3.data.get('details', {}))

    # ------------------------------------------------------------------ #
    # Test 3 — Login returns tokens; wrong password / unknown user fails
    # ------------------------------------------------------------------ #
    def test_login_success_and_wrong_password_failure(self):
        """
        POST /api/auth/login
        - Correct credentials return JWT access + refresh tokens and profile.
        - Wrong password returns 400 with an 'error' key.
        - Unknown username returns 400 with an 'error' key.
        - Login by email address (instead of username) also works.
        """
        # Register user first
        self.client.post(self.register_url, self.student_data, format='json')

        # Correct login via username
        login_res = self.client.post(self.login_url, {
            'username': 'rahul_sharma',
            'password': 'SecurePassword123!',
        }, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', login_res.data)
        self.assertIn('access', login_res.data['tokens'])
        self.assertIn('refresh', login_res.data['tokens'])
        self.assertEqual(login_res.data['profile']['college_roll_number'], 'CS-2026-042')

        # Correct login via email
        email_login_res = self.client.post(self.login_url, {
            'username': 'rahul@campus.edu',
            'password': 'SecurePassword123!',
        }, format='json')
        self.assertEqual(email_login_res.status_code, status.HTTP_200_OK)

        # Wrong password
        bad_login = self.client.post(self.login_url, {
            'username': 'rahul_sharma',
            'password': 'WrongPassword999',
        }, format='json')
        self.assertEqual(bad_login.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', bad_login.data)

        # Non-existent user
        ghost_login = self.client.post(self.login_url, {
            'username': 'ghost_user',
            'password': 'AnyPassword123',
        }, format='json')
        self.assertEqual(ghost_login.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', ghost_login.data)

    # ------------------------------------------------------------------ #
    # Test 4 — JWT-protected profile: GET, PUT budget, token refresh
    # ------------------------------------------------------------------ #
    def test_get_and_update_monthly_budget_limit_with_jwt(self):
        """
        GET/PUT /api/profile  (requires Bearer token)
        - Unauthenticated access returns 401.
        - Authenticated GET returns the profile.
        - PUT with a new budget limit updates the database.
        - POST /api/auth/token/refresh/ returns a new access token.
        - A user registered without a budget limit has is_onboarded=False.
        """
        # ── Register with budget ──────────────────────────────────────
        reg_res = self.client.post(self.register_url, self.student_data, format='json')
        self.assertEqual(reg_res.status_code, status.HTTP_201_CREATED)
        access_token = reg_res.data['tokens']['access']
        refresh_token = reg_res.data['tokens']['refresh']

        # ── Unauthenticated GET must return 401 ───────────────────────
        unauth_res = self.client.get(self.profile_url)
        self.assertEqual(unauth_res.status_code, status.HTTP_401_UNAUTHORIZED)

        # ── Authenticated GET ─────────────────────────────────────────
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        get_res = self.client.get(self.profile_url)
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(get_res.data['college_roll_number'], 'CS-2026-042')
        self.assertTrue(get_res.data['is_onboarded'])

        # ── PUT to update budget limit and income ─────────────────────
        update_res = self.client.put(self.profile_url, {
            'monthly_budget_limit': '850.00',
            'monthly_income': '1500.00',
        }, format='json')
        self.assertEqual(update_res.status_code, status.HTTP_200_OK)
        self.assertEqual(float(update_res.data['profile']['monthly_budget_limit']), 850.00)
        self.assertEqual(float(update_res.data['profile']['monthly_income']), 1500.00)

        # Verify persisted in DB
        profile = UserProfile.objects.get(college_roll_number='CS-2026-042')
        self.assertEqual(float(profile.monthly_budget_limit), 850.00)

        # ── Token refresh ─────────────────────────────────────────────
        self.client.credentials()  # clear auth header
        refresh_res = self.client.post(self.refresh_url, {
            'refresh': refresh_token,
        }, format='json')
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_res.data)

        # ── is_onboarded=False for user without budget set ────────────
        no_budget_data = {
            'username': 'priya_no_budget',
            'email': 'priya@campus.edu',
            'password': 'SecurePass456!',
            'college_roll_number': 'EC-2026-001',
            # No monthly_budget_limit sent → defaults to 0
        }
        nb_res = self.client.post(self.register_url, no_budget_data, format='json')
        self.assertEqual(nb_res.status_code, status.HTTP_201_CREATED)
        self.assertFalse(nb_res.data['profile']['is_onboarded'])
