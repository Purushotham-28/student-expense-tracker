from django.utils import timezone
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
    ManualExpenseSerializer,
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

    auto_count = stmt.transactions.filter(status=Transaction.ParseStatus.AUTO, is_deleted=False).count()
    verify_count = stmt.transactions.filter(status=Transaction.ParseStatus.VERIFY, is_deleted=False).count()
    pending_count = stmt.transactions.filter(status=Transaction.ParseStatus.PENDING, is_deleted=False).count()
    duplicate_count = stmt.duplicate_count

    return Response({
        'message': f'Successfully parsed {stmt.transaction_count} transaction(s)' + (f' ({duplicate_count} duplicate(s) flagged).' if duplicate_count else '.'),
        'statement': StatementSummarySerializer(stmt).data,
        'summary': {
            'total_transactions': stmt.transaction_count,
            'duplicate_count': duplicate_count,
            'auto_count': auto_count,
            'verify_count': verify_count,
            'pending_count': pending_count,
            'date_from': str(stmt.date_from) if stmt.date_from else None,
            'date_to':   str(stmt.date_to)   if stmt.date_to   else None,
            'bank_format': stmt.bank_format,
        },
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_statements(request):
    """GET /api/statements/ — return the authenticated user's active (non-deleted) uploads."""
    stmts = Statement.objects.filter(user=request.user, is_deleted=False).order_by('-uploaded_at')[:50]
    return Response(StatementSummarySerializer(stmts, many=True).data)


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def statement_detail(request, pk):
    """
    GET /api/statements/<pk>/ — full statement with transactions.
    DELETE /api/statements/<pk>/ — soft-delete statement and all associated transactions.
    """
    if request.method == 'GET':
        try:
            stmt = Statement.objects.get(pk=pk, user=request.user, is_deleted=False)
        except Statement.DoesNotExist:
            return Response({'error': 'Statement not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(StatementSerializer(stmt).data)

    elif request.method == 'DELETE':
        try:
            stmt = Statement.objects.get(pk=pk, user=request.user, is_deleted=False)
        except Statement.DoesNotExist:
            return Response({'error': 'Statement not found or already deleted.'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        stmt.is_deleted = True
        stmt.deleted_at = now
        stmt.save(update_fields=['is_deleted', 'deleted_at'])

        deleted_txs = stmt.transactions.filter(is_deleted=False).update(
            is_deleted=True,
            deleted_at=now,
        )

        return Response({
            'message': f'Statement "{stmt.original_filename}" and {deleted_txs} associated transaction(s) deleted.',
            'statement_id': stmt.pk,
            'deleted_transactions_count': deleted_txs,
            'payee_mapping_preserved': True,
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def restore_statement_view(request, pk):
    """
    POST /api/statements/<pk>/restore/
    Restores a soft-deleted statement and its transactions.
    """
    try:
        stmt = Statement.objects.get(pk=pk, user=request.user, is_deleted=True)
    except Statement.DoesNotExist:
        return Response({'error': 'Deleted statement not found.'}, status=status.HTTP_404_NOT_FOUND)

    stmt.is_deleted = False
    stmt.deleted_at = None
    stmt.save(update_fields=['is_deleted', 'deleted_at'])

    restored_txs = stmt.transactions.filter(is_deleted=True).update(
        is_deleted=False,
        deleted_at=None,
    )

    return Response({
        'message': f'Statement "{stmt.original_filename}" and {restored_txs} transaction(s) restored.',
        'statement_id': stmt.pk,
        'restored_transactions_count': restored_txs,
    }, status=status.HTTP_200_OK)


# ── Phase 3 — Hybrid Categorization & Payee Mappings ────────────────────────

from .models import PayeeMapping, Transaction  # noqa: E402
from .serializers import PayeeMappingSerializer, TransactionSerializer  # noqa: E402
from .services.categorization_service import (  # noqa: E402
    categorize_transaction,
    normalize_payee,
    CATEGORIES,
)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def payee_mappings_view(request):
    """
    GET /api/payee-mappings/ — list all user mappings
    POST /api/payee-mappings/ — create or update a payee mapping
      Payload: { "payee_name": "...", "upi_id": "...", "category": "Food" }
      or { "payee_key": "...", "category": "Food" }
    """
    if request.method == 'GET':
        mappings = PayeeMapping.objects.filter(user=request.user)
        return Response(PayeeMappingSerializer(mappings, many=True).data)

    data = request.data.copy()
    payee_key = data.get('payee_key')
    if not payee_key:
        payee_key = normalize_payee(data.get('payee_name'), data.get('upi_id'))

    if not payee_key:
        return Response(
            {'error': 'payee_key, payee_name, or upi_id is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    category = data.get('category')
    if not category or category not in CATEGORIES:
        return Response(
            {'error': f"Valid category required. Must be one of: {CATEGORIES}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    mapping, created = PayeeMapping.objects.get_or_create(
        user=request.user,
        payee_key=payee_key,
        defaults={'category': category, 'times_confirmed': 1},
    )
    if not created:
        mapping.category = category
        mapping.times_confirmed += 1
        mapping.save(update_fields=['category', 'times_confirmed', 'updated_at'])

    return Response(
        PayeeMappingSerializer(mapping).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def categorize_transaction_view(request, pk):
    """
    POST /api/transactions/<pk>/categorize/
    Runs hybrid categorization on a single transaction and saves the result.
    """
    try:
        tx = Transaction.objects.get(pk=pk, user=request.user)
    except Transaction.DoesNotExist:
        return Response({'error': 'Transaction not found.'}, status=status.HTTP_404_NOT_FOUND)

    cat, conf, source = categorize_transaction(tx, save=True)
    return Response({
        'transaction_id': tx.pk,
        'category': cat,
        'confidence': conf,
        'source': source,
        'transaction': TransactionSerializer(tx).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def categorize_statement_view(request, pk):
    """
    POST /api/statements/<pk>/categorize/
    Categorizes all transactions for a given statement.
    """
    try:
        stmt = Statement.objects.get(pk=pk, user=request.user)
    except Statement.DoesNotExist:
        return Response({'error': 'Statement not found.'}, status=status.HTTP_404_NOT_FOUND)

    txns = stmt.transactions.all()
    results = []
    for tx in txns:
        cat, conf, src = categorize_transaction(tx, save=True)
        results.append({
            'transaction_id': tx.pk,
            'category': cat,
            'confidence': conf,
            'source': src,
        })

    return Response({
        'statement_id': stmt.pk,
        'categorized_count': len(results),
        'results': results,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_transactions_view(request):
    """
    GET /api/transactions?status=verify|pending|auto|duplicate|deleted|all&page=1&page_size=20
    Filters transactions by status, with pagination.
    Soft-deleted transactions are filtered out by default unless status=deleted.
    """
    status_filter = request.query_params.get('status', 'all').lower().strip()
    active_user_txs = Transaction.objects.filter(user=request.user, is_deleted=False)
    deleted_user_txs = Transaction.objects.filter(user=request.user, is_deleted=True)

    # Global breakdown counts for the user
    counts = {
        'all': active_user_txs.count(),
        'auto': active_user_txs.filter(status=Transaction.ParseStatus.AUTO).count(),
        'verify': active_user_txs.filter(status=Transaction.ParseStatus.VERIFY).count(),
        'pending': active_user_txs.filter(status=Transaction.ParseStatus.PENDING).count(),
        'duplicate': active_user_txs.filter(is_duplicate=True).count(),
        'deleted': deleted_user_txs.count(),
    }

    # Apply status filter
    if status_filter == 'deleted':
        queryset = deleted_user_txs.order_by('-deleted_at', '-id')
    elif status_filter == 'duplicate':
        queryset = active_user_txs.filter(is_duplicate=True).order_by('-date', '-id')
    elif status_filter in ['auto', 'verify', 'pending']:
        queryset = active_user_txs.filter(status=status_filter)
        if status_filter == 'pending':
            queryset = queryset.order_by('-amount', '-date', '-id')
        else:
            queryset = queryset.order_by('-date', '-id')
    else:
        queryset = active_user_txs.order_by('-date', '-id')

    # Pagination
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
    except (ValueError, TypeError):
        page_size = 20

    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    page_items = queryset[start:end]

    total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count > 0 else 1

    return Response({
        'count': total_count,
        'total_pages': total_pages,
        'current_page': page,
        'page_size': page_size,
        'counts': counts,
        'results': TransactionSerializer(page_items, many=True).data,
    })


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_transaction_view(request, pk):
    """
    DELETE /api/transactions/<pk>/
    Soft-deletes a single transaction. Preserves PayeeMapping rules.
    """
    try:
        tx = Transaction.objects.get(pk=pk, user=request.user, is_deleted=False)
    except Transaction.DoesNotExist:
        return Response({'error': 'Transaction not found or already deleted.'}, status=status.HTTP_404_NOT_FOUND)

    tx.is_deleted = True
    tx.deleted_at = timezone.now()
    tx.save(update_fields=['is_deleted', 'deleted_at'])

    return Response({
        'message': 'Transaction moved to recently deleted.',
        'id': tx.pk,
        'payee_mapping_preserved': True,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def restore_transaction_view(request, pk):
    """
    POST /api/transactions/<pk>/restore/
    Restores a soft-deleted transaction.
    """
    try:
        tx = Transaction.objects.get(pk=pk, user=request.user, is_deleted=True)
    except Transaction.DoesNotExist:
        return Response({'error': 'Deleted transaction not found.'}, status=status.HTTP_404_NOT_FOUND)

    tx.is_deleted = False
    tx.deleted_at = None
    tx.save(update_fields=['is_deleted', 'deleted_at'])

    return Response({
        'message': 'Transaction restored successfully.',
        'id': tx.pk,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_delete_transactions_view(request):
    """
    POST /api/transactions/bulk-delete/
    Payload: { "ids": [1, 2, 3] }
    Soft-deletes multiple transactions. Preserves PayeeMapping rules.
    """
    ids = request.data.get('ids', [])
    if not isinstance(ids, list) or not ids:
        return Response({'error': 'Please provide a non-empty list of transaction ids.'}, status=status.HTTP_400_BAD_REQUEST)

    now = timezone.now()
    count = Transaction.objects.filter(
        id__in=ids,
        user=request.user,
        is_deleted=False,
    ).update(is_deleted=True, deleted_at=now)

    return Response({
        'message': f'{count} transaction(s) moved to recently deleted.',
        'deleted_count': count,
        'payee_mapping_preserved': True,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_restore_transactions_view(request):
    """
    POST /api/transactions/bulk-restore/
    Payload: { "ids": [1, 2, 3] }
    Restores multiple soft-deleted transactions.
    """
    ids = request.data.get('ids', [])
    if not isinstance(ids, list) or not ids:
        return Response({'error': 'Please provide a non-empty list of transaction ids.'}, status=status.HTTP_400_BAD_REQUEST)

    count = Transaction.objects.filter(
        id__in=ids,
        user=request.user,
        is_deleted=True,
    ).update(is_deleted=False, deleted_at=None)

    return Response({
        'message': f'{count} transaction(s) restored successfully.',
        'restored_count': count,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manual_transaction_view(request):
    """
    POST /api/transactions/manual/
    Creates a single manual expense entry for fast daily logging.
    source="manual", status="confirmed", confidence=1.0.
    Skips the auto-categorization pipeline because user selected category directly.
    Checks if payee has PayeeMapping; if not, offers to save it as a mapping for future auto-categorization.
    """
    serializer = ManualExpenseSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'error': 'Invalid expense data',
            'details': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    amount = data['amount']
    category = data['category']
    payee_name = data.get('payee_name', '').strip()
    txn_date = data.get('date') or date.today()
    payment_mode = data.get('payment_mode') or 'UPI'
    save_mapping = data.get('save_mapping', False)

    tx = Transaction.objects.create(
        user=request.user,
        amount=amount,
        category=category,
        payee_name=payee_name,
        date=txn_date,
        is_debit=True,
        source="manual",
        payment_mode=payment_mode,
        status=Transaction.ParseStatus.CONFIRMED,
        confidence=1.0,
        categorization_layer="manual",
        remark=f"Manual entry ({payment_mode})" if not payee_name else f"{payee_name} ({payment_mode})"
    )

    offer_save_mapping = False
    from .services.categorization_service import normalize_payee
    payee_key = normalize_payee(payee_name) if payee_name else ""
    if payee_key:
        mapping_exists = PayeeMapping.objects.filter(user=request.user, payee_key=payee_key).exists()
        if not mapping_exists:
            if save_mapping:
                PayeeMapping.objects.create(
                    user=request.user,
                    payee_key=payee_key,
                    category=category,
                    times_confirmed=1,
                )
            else:
                offer_save_mapping = True

    return Response({
        'message': 'Expense recorded successfully',
        'transaction': TransactionSerializer(tx).data,
        'offer_save_mapping': offer_save_mapping,
        'payee_key': payee_key,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_transaction_view(request, pk):
    """
    POST /api/transactions/{id}/confirm
    Body: { "category": "Food", "apply_to_all": true }
    Action:
      1. Updates the transaction (status="auto", confidence=1.0, category=category).
      2. Upserts PayeeMapping for this user + payee_key (increment times_confirmed).
      3. Re-applies that mapping to other transactions from this user with the same
         payee_key that are still "verify" or "pending".
    """
    try:
        tx = Transaction.objects.get(pk=pk, user=request.user)
    except Transaction.DoesNotExist:
        return Response({'error': 'Transaction not found.'}, status=status.HTTP_404_NOT_FOUND)

    category = request.data.get('category')
    if not category or category not in CATEGORIES:
        return Response(
            {'error': f"Valid category is required. Must be one of: {CATEGORIES}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    apply_to_all = request.data.get('apply_to_all', True)
    if isinstance(apply_to_all, str):
        apply_to_all = apply_to_all.lower() in ('true', '1', 'yes')

    # 1 — Update current transaction
    tx.category = category
    tx.confidence = 1.0
    tx.status = Transaction.ParseStatus.AUTO
    tx.save(update_fields=['category', 'confidence', 'status'])

    # 2 — Upsert PayeeMapping
    payee_key = normalize_payee(tx.payee_name, tx.upi_id)
    mapping = None
    if payee_key:
        mapping, created = PayeeMapping.objects.get_or_create(
            user=request.user,
            payee_key=payee_key,
            defaults={'category': category, 'times_confirmed': 1},
        )
        if not created:
            mapping.category = category
            mapping.times_confirmed += 1
            mapping.save(update_fields=['category', 'times_confirmed', 'updated_at'])

    # 3 — Re-apply to other 'verify' or 'pending' transactions for this user
    updated_others_count = 0
    if apply_to_all and payee_key:
        pending_or_verify = Transaction.objects.filter(
            user=request.user,
            status__in=[Transaction.ParseStatus.VERIFY, Transaction.ParseStatus.PENDING],
        ).exclude(pk=tx.pk)

        matching_ids = []
        for other in pending_or_verify:
            if normalize_payee(other.payee_name, other.upi_id) == payee_key:
                matching_ids.append(other.pk)

        if matching_ids:
            updated_others_count = Transaction.objects.filter(pk__in=matching_ids).update(
                category=category,
                confidence=1.0,
                status=Transaction.ParseStatus.AUTO,
            )

    return Response({
        'message': f"Confirmed category '{category}'. Applied to {updated_others_count + 1} transaction(s).",
        'transaction': TransactionSerializer(tx).data,
        'mapping': PayeeMappingSerializer(mapping).data if mapping else None,
        'payee_key': payee_key,
        'times_confirmed': mapping.times_confirmed if mapping else 1,
        'updated_count': updated_others_count + 1,
    }, status=status.HTTP_200_OK)


# ── Phase 5 — Forecasting & Cash-Flow Runway (What-If Simulator) ───────────

from .services.forecasting_service import (  # noqa: E402
    calculate_cash_flow_runway,
    simulate_whatif_adjustments,
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def runway_view(request):
    """
    GET /api/planning/runway
    Query params:
      - current_balance: optional float override
    Returns:
      - current_balance
      - runway_date
      - runway_days
      - is_exhausted
      - daily_burn_rate
      - forecast_series (historical actuals + 30-day forecast with remaining balance trajectory)
      - category_shares
      - method ('prophet' | 'arima' | 'baseline_average')
    """
    bal_param = request.query_params.get('current_balance')
    current_balance = None
    if bal_param is not None:
        try:
            current_balance = float(bal_param)
        except ValueError:
            pass

    data = calculate_cash_flow_runway(user=request.user, current_balance=current_balance)
    return Response(data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def whatif_view(request):
    """
    POST /api/planning/whatif
    Body can be:
      - { "category": "Food", "reduce_percent": 30 }
      - { "adjustments": [{"category": "Food", "reduce_percent": 30}, ...], "current_balance": 15000 }
      - { "adjustments": { "Food": 30, "Entertainment": 50 } }
    Returns:
      - original_runway_date, original_runway_days
      - adjusted_runway_date, adjusted_runway_days
      - days_saved, money_saved_30d
      - adjusted_daily_burn
      - adjusted_forecast_series
    """
    current_balance = request.data.get('current_balance')
    if current_balance is not None:
        try:
            current_balance = float(current_balance)
        except ValueError:
            current_balance = None

    data = simulate_whatif_adjustments(
        user=request.user,
        adjustments=request.data,
        current_balance=current_balance,
    )
    return Response(data, status=status.HTTP_200_OK)


# ── Phase 6 — Goal Planner & Adaptive Savings ──────────────────────────────

from .models import Goal  # noqa: E402
from .serializers import GoalSerializer  # noqa: E402
from .services.goal_service import (  # noqa: E402
    calculate_goal_metrics,
    contribute_to_goal,
    check_goal_progress_and_suggest_cut,
)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def goals_view(request):
    """
    GET /api/goals/?status=active|done|all
      Lists user's goals with calculated weekly targets, plus background progress check.
    POST /api/goals/
      Creates a new savings goal.
      Payload: { "name": "Laptop", "target_amount": 60000, "deadline": "2026-12-31", "saved_so_far": 0 }
    """
    if request.method == 'GET':
        status_filter = request.query_params.get('status', 'all').lower()
        qs = Goal.objects.filter(user=request.user)
        if status_filter in ['active', 'done']:
            qs = qs.filter(status=status_filter)

        goals_data = GoalSerializer(qs, many=True).data

        # Background check of actual savings rate vs required rate
        evaluation = check_goal_progress_and_suggest_cut(request.user)

        total_target = sum(float(g.target_amount) for g in qs)
        total_saved = sum(float(g.saved_so_far) for g in qs)
        active_weekly_target = sum(g.weekly_target for g in qs if g.status == Goal.Status.ACTIVE)

        return Response({
            'goals': goals_data,
            'summary': {
                'total_goals': len(goals_data),
                'total_target_amount': round(total_target, 2),
                'total_saved_so_far': round(total_saved, 2),
                'total_weekly_target': round(active_weekly_target, 2),
                'overall_progress_pct': round((total_saved / total_target * 100) if total_target > 0 else 0.0, 1),
            },
            'evaluation': evaluation,
        }, status=status.HTTP_200_OK)

    # POST create
    serializer = GoalSerializer(data=request.data)
    if serializer.is_valid():
        goal = serializer.save(user=request.user)
        # Check if saved_so_far already reached target
        if float(goal.saved_so_far) >= float(goal.target_amount):
            goal.status = Goal.Status.DONE
            goal.save(update_fields=['status'])
        return Response(GoalSerializer(goal).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def goal_detail_view(request, pk):
    """
    GET /api/goals/{id}/ — retrieve goal detail
    PUT/PATCH /api/goals/{id}/ — update goal
    DELETE /api/goals/{id}/ — delete goal
    """
    try:
        goal = Goal.objects.get(pk=pk, user=request.user)
    except Goal.DoesNotExist:
        return Response({'error': 'Goal not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(GoalSerializer(goal).data)

    if request.method == 'DELETE':
        goal.delete()
        return Response({'success': True, 'message': 'Goal deleted successfully.'}, status=status.HTTP_200_OK)

    # PUT or PATCH
    partial = (request.method == 'PATCH')
    serializer = GoalSerializer(goal, data=request.data, partial=partial)
    if serializer.is_valid():
        updated_goal = serializer.save()
        if float(updated_goal.saved_so_far) >= float(updated_goal.target_amount):
            updated_goal.status = Goal.Status.DONE
            updated_goal.save(update_fields=['status'])
        return Response(GoalSerializer(updated_goal).data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def goal_contribute_view(request, pk):
    """
    POST /api/goals/{id}/contribute
    Body: { "amount": 500 }
    Increases saved_so_far, adapts weekly target, and marks done if goal reached.
    """
    try:
        goal = Goal.objects.get(pk=pk, user=request.user)
    except Goal.DoesNotExist:
        return Response({'error': 'Goal not found.'}, status=status.HTTP_404_NOT_FOUND)

    amount_raw = request.data.get('amount')
    if amount_raw is None:
        return Response({'error': 'Contribution amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return Response({'error': 'Amount must be a positive number.'}, status=status.HTTP_400_BAD_REQUEST)

    updated_goal, just_completed = contribute_to_goal(goal, amount)

    return Response({
        'goal': GoalSerializer(updated_goal).data,
        'amount_contributed': amount,
        'goal_completed': just_completed or (updated_goal.status == Goal.Status.DONE),
        'message': f"Successfully contributed ₹{amount:,.2f} towards '{updated_goal.name}'!",
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def goal_suggestion_view(request, pk=None):
    """
    GET /api/goals/suggestion/ or GET /api/goals/{id}/suggestion/
    'I'm behind — what should I cut?' intelligent background diagnostic.
    Compares recent savings rate against required weekly target, flags if behind,
    and uses Phase 5 forecasting to suggest optimal discretionary category cuts.
    """
    goal_id = pk or request.query_params.get('goal_id')
    if goal_id is not None:
        try:
            goal_id = int(goal_id)
        except (ValueError, TypeError):
            goal_id = None

    suggestion = check_goal_progress_and_suggest_cut(user=request.user, goal_id=goal_id)
    return Response(suggestion, status=status.HTTP_200_OK)


# ── Phase 7 — Financial Health Score ────────────────────────────────────────

from .services.health_score_service import get_user_financial_health_score  # noqa: E402


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def health_score_view(request):
    """
    GET /api/planning/health-score
    Computes a 0-100 financial health score for the current month combining:
      - Savings rate component (up to 40 pts)
      - Budget adherence component (up to 30 pts)
      - Spending volatility component (up to 30 pts)
    Returns the total score, the three sub-scores, metrics breakdown, and 2-3 generated tips.
    """
    data = get_user_financial_health_score(request.user)
    return Response(data, status=status.HTTP_200_OK)


# ── Phase 8 — AI Chatbox (Claude API with Function Calling) ────────────────

from .models import ChatMessage  # noqa: E402
from .serializers import ChatMessageSerializer  # noqa: E402
from .services.chat_service import process_chat_message  # noqa: E402


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def chat_view(request):
    """
    POST /api/chat — Send a message, trigger tool loop with Claude, and get AI guidance.
      Payload: { "message": "How much did I spend on food?" }
    GET /api/chat — Retrieve recent chat message history for the student.
    """
    if request.method == 'GET':
        limit = int(request.query_params.get('limit', 50))
        messages = ChatMessage.objects.filter(user=request.user).order_by('created_at')[:limit]
        return Response(ChatMessageSerializer(messages, many=True).data, status=status.HTTP_200_OK)

    message_content = request.data.get('message', '').strip()
    if not message_content:
        return Response({'error': 'Message content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)

    result = process_chat_message(user=request.user, message_content=message_content)
    return Response(result, status=status.HTTP_200_OK)


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def chat_history_view(request):
    """
    GET /api/chat/history — Fetch full chronological conversation history.
    DELETE /api/chat/history — Clear conversation history.
    """
    if request.method == 'DELETE':
        ChatMessage.objects.filter(user=request.user).delete()
        return Response({'success': True, 'message': 'Chat history cleared.'}, status=status.HTTP_200_OK)

    messages = ChatMessage.objects.filter(user=request.user).order_by('created_at')
    return Response(ChatMessageSerializer(messages, many=True).data, status=status.HTTP_200_OK)


# ── Phase 9 — Dashboard Summary & Analytics ─────────────────────────────────

from .services.dashboard_service import get_dashboard_summary  # noqa: E402


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_summary_view(request):
    """
    GET /api/dashboard/summary/
    Unified demo-ready dashboard summary:
      - Budget vs actual this month
      - Category breakdown & active budget alerts (80% and 100% caps)
      - Runway forecast & burn rate
      - Goals progress & velocity alert
      - Financial Health score card
      - Verification pipeline status & recent transactions
    """
    data = get_dashboard_summary(request.user)
    return Response(data, status=status.HTTP_200_OK)
