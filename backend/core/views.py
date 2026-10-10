from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile, Statement
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserProfileSerializer,
    StatementSerializer,
    StatementSummarySerializer,
)
from .services.statement_service import validate_upload, process_uploaded_statement


# ── Health ──────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    return Response({
        'status': 'healthy',
        'app': 'student-expense-tracker',
        'version': '1.0.0',
        'message': 'Student Expense Tracker API is running',
    })


# ── Auth ────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'error': 'Registration failed',
            'details': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    profile = user.profile
    refresh = RefreshToken.for_user(user)

    return Response({
        'message': 'Student registered successfully',
        'tokens': {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        },
        'profile': UserProfileSerializer(profile).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        error_msg = 'Invalid username or password'
        if 'non_field_errors' in serializer.errors:
            error_msg = serializer.errors['non_field_errors'][0]
        elif serializer.errors:
            first_field = next(iter(serializer.errors))
            error_msg = f"{first_field}: {serializer.errors[first_field][0]}"

        return Response({
            'error': error_msg,
            'details': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    return Response({
        'message': 'Login successful',
        'tokens': {
            'access': data['access'],
            'refresh': data['refresh'],
        },
        'profile': UserProfileSerializer(data['profile']).data,
    }, status=status.HTTP_200_OK)


# ── Profile ─────────────────────────────────────────────────────────────────

@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={'college_roll_number': f'ROLL-{request.user.id}'},
    )

    if request.method == 'GET':
        return Response(UserProfileSerializer(profile).data)

    serializer = UserProfileSerializer(profile, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response({
            'error': 'Profile update failed',
            'details': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    updated_profile = serializer.save()
    return Response({
        'message': 'Profile updated successfully',
        'profile': UserProfileSerializer(updated_profile).data,
    })


# ── Statement Upload ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_statement(request):
    """
    POST /api/statements/upload
    Accepts a multipart file upload (PDF or CSV bank statement).

    Response on success:
      {
        "message": "...",
        "statement": { ...StatementSerializer... },
        "summary": {
          "total_transactions": 42,
          "date_from": "2026-09-01",
          "date_to":   "2026-09-30",
          "bank_format": "sbi_csv",
        }
      }
    """
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return Response(
            {'error': 'No file provided. Upload a PDF or CSV bank statement.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    error = validate_upload(uploaded_file.name, uploaded_file.size)
    if error:
        return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

    stmt = process_uploaded_statement(
        user=request.user,
        file_obj=uploaded_file,
        filename=uploaded_file.name,
    )

    if stmt.status == Statement.Status.FAILED:
        return Response({
            'error': stmt.error_message or 'Parsing failed. Please check the file format.',
            'statement_id': stmt.pk,
        }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    return Response({
        'message': f'Successfully parsed {stmt.transaction_count} transaction(s).',
        'statement': StatementSummarySerializer(stmt).data,
        'summary': {
            'total_transactions': stmt.transaction_count,
            'date_from': str(stmt.date_from) if stmt.date_from else None,
            'date_to':   str(stmt.date_to)   if stmt.date_to   else None,
            'bank_format': stmt.bank_format,
        },
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_statements(request):
    """GET /api/statements/ — return the authenticated user's past uploads."""
    stmts = Statement.objects.filter(user=request.user).order_by('-uploaded_at')[:50]
    return Response(StatementSummarySerializer(stmts, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def statement_detail(request, pk):
    """GET /api/statements/<pk>/ — full statement with transactions."""
    try:
        stmt = Statement.objects.get(pk=pk, user=request.user)
    except Statement.DoesNotExist:
        return Response({'error': 'Statement not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(StatementSerializer(stmt).data)
