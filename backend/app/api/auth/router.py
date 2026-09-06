import hmac
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.auth.security import AuthenticatedUser, create_access_token, require_user
from app.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthenticatedUser


class AuthConfigResponse(BaseModel):
    provider: str


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config(settings: Settings = Depends(get_settings)) -> AuthConfigResponse:
    return AuthConfigResponse(provider="external" if settings.use_external_auth else "demo")


@router.get("/google/start", include_in_schema=False)
async def google_start(
    redirect_after: str = Query(...),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if not settings.use_external_auth or not settings.auth_api_base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="External auth is not configured",
        )

    query = urlencode({"redirect_after": redirect_after})
    target = f"{settings.auth_api_url(settings.auth_api_login_path)}?{query}"
    return RedirectResponse(target)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    if settings.use_external_auth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This deployment uses Google sign-in. Use GET /api/auth/google/start instead.",
        )

    email_matches = hmac.compare_digest(payload.email, settings.demo_user_email)
    password_matches = hmac.compare_digest(payload.password, settings.demo_user_password)

    if not email_matches or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user = AuthenticatedUser(
        email=settings.demo_user_email,
        name=settings.demo_user_name,
        role="platform-admin",
    )
    return LoginResponse(access_token=create_access_token(user, settings), user=user)


@router.get("/me", response_model=AuthenticatedUser)
async def me(user: AuthenticatedUser = Depends(require_user)) -> AuthenticatedUser:
    return user
