from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserProfile
from .serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    return Response({
        'status': 'healthy',
        'app': 'student-expense-tracker',
        'version': '1.0.0',
        'message': 'Student Expense Tracker API is running'
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'error': 'Registration failed',
            'details': serializer.errors
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
        'profile': UserProfileSerializer(profile).data
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_user(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        # Flatten error messages for clean UI display
        error_msg = "Invalid username or password"
        if 'non_field_errors' in serializer.errors:
            error_msg = serializer.errors['non_field_errors'][0]
        elif serializer.errors:
            first_field = next(iter(serializer.errors))
            error_msg = f"{first_field}: {serializer.errors[first_field][0]}"

        return Response({
            'error': error_msg,
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    return Response({
        'message': 'Login successful',
        'tokens': {
            'access': data['access'],
            'refresh': data['refresh'],
        },
        'profile': UserProfileSerializer(data['profile']).data
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def user_profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={'college_roll_number': f"ROLL-{request.user.id}"}
    )

    if request.method == 'GET':
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method in ['PUT', 'PATCH']:
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({
                'error': 'Profile update failed',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        updated_profile = serializer.save()
        return Response({
            'message': 'Profile updated successfully',
            'profile': UserProfileSerializer(updated_profile).data
        }, status=status.HTTP_200_OK)
