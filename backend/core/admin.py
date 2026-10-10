from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserProfile, Statement, Transaction, PayeeMapping


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


class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    readonly_fields = (
        "date", "time", "amount", "is_debit", "payee_name",
        "upi_id", "remark", "category", "confidence", "status",
    )
    fields = readonly_fields
    show_change_link = True


@admin.register(Statement)
class StatementAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "original_filename", "file_type", "bank_format",
        "status", "transaction_count", "date_from", "date_to", "uploaded_at",
    )
    list_filter = ("status", "file_type", "bank_format", "uploaded_at")
    search_fields = ("user__username", "original_filename")
    readonly_fields = ("uploaded_at", "processed_at")
    ordering = ("-uploaded_at",)
    inlines = [TransactionInline]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "date", "amount", "is_debit",
        "payee_name", "category", "confidence", "status", "created_at",
    )
    list_filter = ("is_debit", "category", "status", "date")
    search_fields = ("payee_name", "upi_id", "remark", "user__username")
    readonly_fields = ("created_at",)
    ordering = ("-date", "-created_at")


@admin.register(PayeeMapping)
class PayeeMappingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "payee_key", "category", "times_confirmed", "updated_at")
    list_filter = ("category", "updated_at")
    search_fields = ("user__username", "payee_key")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at",)

