from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    college_roll_number = models.CharField(max_length=50, unique=True, help_text="Unique student/college roll number")
    monthly_income = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Optional monthly stipend or allowance")
    monthly_budget_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Target spending limit per month")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.college_roll_number})"
