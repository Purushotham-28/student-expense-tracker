from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserProfile

class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    is_onboarded = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'username',
            'email',
            'college_roll_number',
            'monthly_income',
            'monthly_budget_limit',
            'is_onboarded',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'username', 'email', 'created_at', 'updated_at']

    def get_is_onboarded(self, obj):
        # A student is considered onboarded once they have set a budget limit > 0
        return bool(obj.monthly_budget_limit and obj.monthly_budget_limit > 0)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    college_roll_number = serializers.CharField(max_length=50, required=True)
    monthly_income = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    monthly_budget_limit = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.00)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'college_roll_number', 'monthly_income', 'monthly_budget_limit']

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        if not value:
            raise serializers.ValidationError("Email is required.")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return value

    def validate_college_roll_number(self, value):
        clean_roll = value.strip().upper()
        if not clean_roll:
            raise serializers.ValidationError("College roll number cannot be empty.")
        if UserProfile.objects.filter(college_roll_number__iexact=clean_roll).exists():
            raise serializers.ValidationError("A profile with this college roll number already exists.")
        return clean_roll

    def create(self, validated_data):
        college_roll_number = validated_data.pop('college_roll_number')
        monthly_income = validated_data.pop('monthly_income', None)
        monthly_budget_limit = validated_data.pop('monthly_budget_limit', 0.00)
        password = validated_data.pop('password')

        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=password,
        )

        profile = UserProfile.objects.create(
            user=user,
            college_roll_number=college_roll_number,
            monthly_income=monthly_income,
            monthly_budget_limit=monthly_budget_limit or 0.00,
        )

        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            raise serializers.ValidationError("Must include both username and password.")

        # Allow login via username or email
        user = authenticate(username=username, password=password)
        if not user:
            try:
                user_obj = User.objects.get(email__iexact=username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if not user:
            raise serializers.ValidationError("Invalid credentials. Please verify your username and password.")

        if not user.is_active:
            raise serializers.ValidationError("This user account has been disabled.")

        refresh = RefreshToken.for_user(user)

        # Ensure user profile exists
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={'college_roll_number': f"ROLL-{user.id}"}
        )

        return {
            'user': user,
            'profile': profile,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


# ── Statement & Transaction serializers ────────────────────────────────────

from .models import Statement, Transaction  # noqa: E402


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'id', 'date', 'time', 'amount', 'is_debit',
            'payee_name', 'upi_id', 'remark',
            'category', 'confidence', 'status', 'created_at',
        ]
        read_only_fields = fields


class StatementSerializer(serializers.ModelSerializer):
    transactions = TransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Statement
        fields = [
            'id', 'original_filename', 'file_type', 'bank_format',
            'status', 'error_message', 'transaction_count',
            'date_from', 'date_to', 'uploaded_at', 'processed_at',
            'transactions',
        ]
        read_only_fields = fields


class StatementSummarySerializer(serializers.ModelSerializer):
    """Lightweight version without the full transaction list — used for list views."""

    class Meta:
        model = Statement
        fields = [
            'id', 'original_filename', 'file_type', 'bank_format',
            'status', 'error_message', 'transaction_count',
            'date_from', 'date_to', 'uploaded_at', 'processed_at',
        ]
        read_only_fields = fields
