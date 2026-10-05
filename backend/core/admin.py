from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Student Profile"
    fields = ("college_roll_number", "monthly_income", "monthly_budget_limit", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ("username", "email", "get_roll_number", "is_active", "date_joined")
    search_fields = ("username", "email", "profile__college_roll_number")

    @admin.display(description="Roll Number")
    def get_roll_number(self, obj):
        try:
            return obj.profile.college_roll_number
        except UserProfile.DoesNotExist:
            return "—"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "college_roll_number", "monthly_budget_limit", "monthly_income", "is_onboarded", "created_at")
    list_filter = ("created_at",)
    search_fields = ("college_roll_number", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

    @admin.display(boolean=True, description="Onboarded?")
    def is_onboarded(self, obj):
        return bool(obj.monthly_budget_limit and obj.monthly_budget_limit > 0)


# Re-register User with the custom admin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
