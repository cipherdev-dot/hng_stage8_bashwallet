import logging
from decimal import Decimal
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.wallet_schemas import BalanceResponse, DepositRequest, DepositResponse
from app.services.api_key_service import APIKeyService
from app.services.paystack_service import PaystackService
from app.utils.paystack_webhook import verify_paystack_webhook_signature


logger = logging.getLogger(__name__)

wallet_router = APIRouter()


@wallet_router.post("/deposit", response_model=DepositResponse)
async def initiate_deposit(
    deposit_data: DepositRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Initialize a wallet deposit using Paystack.

    Supports both JWT and API key authentication.
    Creates a pending transaction and returns Paystack authorization URL.

    Args:
        deposit_data: Deposit request with amount.
        request: HTTP request for auth detection.
        db: Database session.

    Returns:
        DepositResponse: Transaction details and payment URL.

    Raises:
        HTTPException: For validation errors or Paystack failures.
    """
    auth_user = None

    # Debug: Log authentication attempt
    logger.info(f"Deposit auth attempt - API key: {'x-api-key' in request.headers}, JWT: {'authorization' in request.headers}")

    # Check for API key authentication first
    if request.headers.get("x-api-key"):
        logger.info("Attempting API key authentication")
        try:
            api_key = request.headers.get("x-api-key")
            api_key_obj, api_key_user = await APIKeyService.validate_api_key(api_key, db)
            if not api_key_user or not api_key_obj:
                logger.warning("API key validation failed - invalid key or user")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
                )
            if "wallet:write" not in api_key_obj.permissions:
                logger.warning("API key missing wallet:write permission")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="API key does not have wallet:write permission",
                )
            auth_user = api_key_user
            logger.info(f"API key auth successful for user: {auth_user.id}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"API key auth error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="API key authentication failed"
            )
    else:
        logger.info("Attempting JWT authentication")
        # Use JWT authentication
        try:
            # Extract auth header
            auth_header = request.headers.get("authorization")
            if not auth_header:
                logger.warning("Missing authorization header")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
                )
            if not auth_header.startswith("Bearer "):
                logger.warning("Authorization header doesn't start with Bearer")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization format"
                )

            # Get token from auth header
            token = auth_header[7:]  
            if not token:
                logger.warning("Empty JWT token")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
                )

            from app.core.security import verify_token
            token_data = verify_token(token)
            user_sub = token_data.get("sub")

            if not user_sub:
                logger.warning("Missing sub claim in JWT")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
                )

            # Get user from database
            from sqlalchemy.future import select
            from app.models.user import User
            result = await db.execute(
                select(User).where(User.google_sub == user_sub)
            )
            auth_user = result.scalars().first()

            if not auth_user:
                logger.warning(f"User not found for Google sub: {user_sub}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
                )

            logger.info(f"JWT auth successful for user: {auth_user.id}")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"JWT authentication error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication"
            )

    try:
        # Check if user has wallet, create if needed
        from sqlalchemy.future import select
        from app.models.wallet import Wallet
        from app.utils.wallet import generate_unique_wallet_number

        user_wallet = await db.execute(
            select(Wallet).where(Wallet.user_id == auth_user.id)
        )
        wallet = user_wallet.scalars().first()

        if not wallet:
            logger.info(f"Auto-creating wallet for user {auth_user.id}")
            wallet_number = await generate_unique_wallet_number(db)
            wallet = Wallet(
                user_id=auth_user.id,
                wallet_number=wallet_number
            )
            db.add(wallet)
            await db.commit()
            await db.refresh(wallet)
            logger.info(f"Auto-created wallet {wallet_number} for user {auth_user.id}")

        # Initialize deposit with Paystack
        paystack_response = await PaystackService.initialize_deposit(
            user=auth_user,
            amount=deposit_data.amount,
            db=db,
            callback_url=f"{request.base_url.scheme}://{request.base_url.netloc}/api/v1/wallet/deposit/callback",
        )

        # Extract authorization URL and reference
        data = paystack_response.get("data", {})
        auth_url = data.get("authorization_url")
        reference = data.get("reference")

        if not auth_url or not reference:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get Paystack payment details",
            )

        user_id = getattr(auth_user, "id", "unknown")
        logger.info(
            f"Deposit initiated for user {user_id}: ₦{deposit_data.amount}, ref: {reference}"
        )

        return DepositResponse(
            transaction_id=reference,
            reference=reference,
            authorization_url=auth_url,
            amount=deposit_data.amount,
            message="Deposit initiated successfully. Complete payment via the authorization URL.",
        )

    except HTTPException:
        raise
    except Exception as e:
        user_id = getattr(auth_user, "id", "unknown")
        logger.error(f"Deposit initiation failed for user {user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@wallet_router.get("/balance", response_model=BalanceResponse)
async def get_wallet_balance(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's wallet balance.

    Supports both JWT and API key authentication.
    Loads user's wallet directly to avoid relationship issues.

    Args:
        request: HTTP request for auth detection.
        db: Database session.

    Returns:
        BalanceResponse: Wallet balance information.

    Raises:
        HTTPException: If user has no wallet or auth fails.
    """
    # Get authenticated user using same logic as deposit endpoint
    auth_user = None

    # Check for API key authentication first
    if request.headers.get("x-api-key"):
        api_key_obj, api_key_user = await APIKeyService.validate_api_key(request.headers.get("x-api-key"), db)
        if not api_key_user or not api_key_obj:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
            )
        auth_user = api_key_user
    else:
        # Use JWT authentication
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
            )

        token = auth_header[7:]  # Remove "Bearer " prefix
        from app.core.security import verify_token
        token_data = verify_token(token)
        user_sub = token_data.get("sub")

        if not user_sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )

        # Get user from database
        from sqlalchemy.future import select
        from app.models.user import User
        result = await db.execute(
            select(User).where(User.google_sub == user_sub)
        )
        auth_user = result.scalars().first()

        if not auth_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
            )

    try:
        # Get wallet directly (avoid relationship loading issues)
        from sqlalchemy.future import select
        from app.models.wallet import Wallet

        wallet_result = await db.execute(
            select(Wallet).where(Wallet.user_id == auth_user.id)
        )
        wallet = wallet_result.scalars().first()

        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet not found. Please contact support.",
            )

        return BalanceResponse(
            wallet_number=wallet.wallet_number,
            balance=f"{wallet.balance:.2f}",
            currency="NGN",
            is_active=wallet.is_active,
        )

    except HTTPException:
        raise
    except Exception as e:
        user_id = getattr(auth_user, "id", "unknown")
        logger.error(f"Failed to get balance for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve wallet balance",
        )


@wallet_router.post("/paystack/webhook")
async def paystack_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle Paystack webhook for payment completion.

    Processes charge.success events and credits wallet balances atomically.
    Implements signature verification and idempotency.

    Args:
        request: Raw HTTP request with webhook data.
        db: Database session.

    Returns:
        dict: Webhook response.
    """
    try:
        # Get raw request body for signature verification
        body = await request.body()
        webhook_data = await request.json()

        # Extract and verify signature
        signature_header = request.headers.get("x-paystack-signature")
        if not signature_header:
            logger.error("Missing Paystack webhook signature")
            return {"status": "error"}, 400

        if not verify_paystack_webhook_signature(body, signature_header):
            logger.error("Invalid Paystack webhook signature")
            logger.error(f"Expected signature for body: {body[:100]}...")
            return {"status": "error"}, 400

        logger.info(f"Received verified Paystack webhook: {webhook_data.get('event')}")

        # Process the webhook
        success = await PaystackService.process_deposit_webhook(webhook_data, db)

        if success:
            return {"status": "success"}
        else:
            logger.error("Webhook processing failed")
            return {"status": "error"}, 500

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return {"status": "error"}, 500
