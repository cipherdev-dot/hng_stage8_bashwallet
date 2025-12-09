
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.user import AuthResponse, UserCreate, UserResponse
from app.utils.wallet import generate_unique_wallet_number

# Set up logger
logger = logging.getLogger(__name__)

auth_router = APIRouter()


def _get_google_auth_url(state: str) -> str:
    """
    Generate Google OAuth2 authorization URL.

    Args:
        state: Random state string for CSRF protection.

    Returns:
        str: Google OAuth URL.
    """
    base_url = "https://accounts.google.com/o/oauth2/auth"
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "scope": "openid email profile",
        "response_type": "code",
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{query_string}"


@auth_router.get("/google", response_class=RedirectResponse)
async def google_auth():
    """
    Initiate Google OAuth2 login flow.

    Generates state token for CSRF protection and redirects to Google.
    """
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth2 not configured",
        )

    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Redirect to Google OAuth
    auth_url = _get_google_auth_url(state)
    return RedirectResponse(url=auth_url, status_code=302)


@auth_router.get("/google/callback", response_model=AuthResponse)
async def google_auth_callback(
    code: str,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Google OAuth2 callback.

    Verifies ID token, creates or finds user, and issues JWT.

    Args:
        code: Authorization code from Google.
        state: State parameter for CSRF protection.
        error: Error from Google OAuth.

    Returns:
        AuthResponse: JWT token and user data.
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth error: {error}"
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code missing"
        )

    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth2 not properly configured"
        )

    try:
        # Get access token from authorization code
        import httpx

        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_redirect_uri,
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data)
            token_response.raise_for_status()
            token_info = token_response.json()

        # Verify ID token
        id_token_value = token_info.get("id_token")
        if not id_token_value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID token missing from response"
            )

        # Verify the ID token with Google's servers
        # Add clock tolerance for development environments
        request_obj = requests.Request()
        id_info = id_token.verify_oauth2_token(
            id_token_value,
            request_obj,
            settings.google_client_id,
            clock_skew_in_seconds=10  
        )

        # Extract user info from verified token
        google_sub = id_info["sub"]
        email = id_info["email"]
        name = id_info.get("name")
        picture = id_info.get("picture")

        logger.info(f"OAuth callback for user with Google sub: {google_sub}")

        # Check if user exists
        result = await db.execute(
            select(User).where(User.google_sub == google_sub)
        )
        user = result.scalars().first()

        if not user:
            # Create new user
            user_data = UserCreate(
                google_sub=google_sub,
                email=email,
                name=name,
                picture=picture
            )
            user = User(**user_data.model_dump())
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"Created new user: {user.id}")

            # Auto-create wallet for new user
            wallet_number = await generate_unique_wallet_number(db)
            wallet = Wallet(
                user_id=user.id,
                wallet_number=wallet_number
            )
            db.add(wallet)
            await db.commit()
            await db.refresh(wallet)
            logger.info(f"Auto-created wallet {wallet_number} for user: {user.id}")

        else:
            logger.info(f"Found existing user: {user.id}")

            # Check if user has wallet
            result = await db.execute(
                select(Wallet).where(Wallet.user_id == user.id)
            )
            wallet = result.scalars().first()

            if not wallet:
                # Auto-create wallet for existing user without one
                wallet_number = await generate_unique_wallet_number(db)
                wallet = Wallet(
                    user_id=user.id,
                    wallet_number=wallet_number
                )
                db.add(wallet)
                await db.commit()
                await db.refresh(wallet)
                logger.info(f"Auto-created wallet {wallet_number} for existing user: {user.id}")

        # Create JWT token
        jwt_token = create_access_token(data={"sub": user.google_sub})

        # Convert SQLAlchemy model to dict for Pydantic validation
        user_dict = {
            "id": user.id,
            "google_sub": user.google_sub,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
            "created_at": user.created_at
        }

        # Return auth response
        user_response = UserResponse.model_validate(user_dict)
        logger.info(f"Successfully issued JWT token for user: {user.id}")
        return AuthResponse(
            access_token=jwt_token,
            user=user_response
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth verification failed: {str(e)}"
        )
