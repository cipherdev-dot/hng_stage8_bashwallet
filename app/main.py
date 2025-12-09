from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import auth_router
from app.api.v1.key_route import keys_router
from app.core.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events. Currently initializes database
    tables on startup.
    """
    # Startup: create tables
    await init_db()
    yield


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Sets up the main application with CORS middleware, health checks,
    and routing for authentication and other endpoints.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Bashwallet API",
        description="Secure wallet service with Paystack integration",
        version="1.0.0",
        lifespan=lifespan
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(keys_router, prefix="/api/v1/keys", tags=["api-keys"])

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """
        Health check endpoint for load balancers and monitoring.

        Returns:
            dict: Health status response.
        """
        return {"status": "healthy"}

    # Root endpoint
    @app.get("/")
    async def root():
        """
        Root endpoint providing basic API information.

        Returns:
            dict: Welcome message.
        """
        return {"message": "Bashwallet API"}

    return app
