# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""JWT authentication utilities."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.events import record_event
from app.core.llm_request import resolve_generation_billing_source
from app.core.safety_fuses import ensure_ai_available, ensure_hosted_user_capacity, hosted_signup_lock
from app.database import get_db
from app.models import AuthIdentity, QuotaReservation, User


logger = logging.getLogger(__name__)
_QUOTA_RESERVATION_OWNER_TOKEN = uuid4().hex

#
# Password hashing
# ----------------
# We intentionally do NOT rely on passlib's bcrypt backend because the
# passlib<->bcrypt compatibility matrix is brittle on newer Python versions.
# Use a stable, stdlib-backed scheme for new hashes, and keep a bcrypt fallback
# verifier for legacy rows.
#
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
SESSION_COOKIE_NAME = "novwr_session"
AUTH_PROVIDER_INVITE = "invite"
AUTH_PROVIDER_GITHUB = "github"
_DEFAULT_INTERNAL_USERNAME_SEED = "user"
_INTERNAL_USERNAME_SUFFIX_HEX_BYTES = 4
_OAUTH_STATE_TOKEN_KIND = "hosted_oauth_state"
DEFAULT_OAUTH_STATE_TTL_SECONDS = 600


def _raise_quota_http_error(*, count: int = 1, have: int | None = None) -> None:
    exhausted = count <= 1
    message = (
        "Generation quota exhausted. Submit feedback to unlock more."
        if exhausted
        else f"Not enough quota for this request (need {count}, have {have if have is not None else 0}). Submit feedback to unlock more."
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "generation_quota_exhausted" if exhausted else "generation_quota_insufficient",
            "message": message,
            "meta": {
                "need": count,
                "have": have,
            },
        },
    )


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        # Legacy support: previously stored bcrypt hashes typically start with "$2".
        # Verify them via the bcrypt library directly to avoid passlib backend issues.
        if hashed.startswith("$2"):
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        return pwd_context.verify(plain, hashed)
    except Exception:
        # Auth must never 500 due to a hash backend issue; treat as invalid credentials.
        return False


def create_access_token(data: dict) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {**data, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _request_is_secure(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return forwarded_proto == "https" or request.url.scheme == "https"


def set_auth_cookie(response: Response, request: Request, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        secure=_request_is_secure(request),
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def issue_user_session(*, response: Response, request: Request, user: User) -> str:
    token = create_access_token({"sub": user.username})
    set_auth_cookie(response, request, token)
    return token


def create_oauth_state_token(
    *,
    provider: str,
    redirect_to: str,
    nonce: str,
    expires_in_seconds: int = DEFAULT_OAUTH_STATE_TTL_SECONDS,
) -> str:
    settings = get_settings()
    normalized_provider = _normalize_auth_provider(provider)
    normalized_redirect = _normalize_provider_user_id(redirect_to)
    normalized_nonce = _normalize_provider_user_id(nonce)
    expire_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, int(expires_in_seconds)))
    payload = {
        "kind": _OAUTH_STATE_TOKEN_KIND,
        "provider": normalized_provider,
        "redirect_to": normalized_redirect,
        "nonce": normalized_nonce,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_oauth_state_token(*, token: str, provider: str) -> dict[str, str]:
    settings = get_settings()
    normalized_provider = _normalize_auth_provider(provider)
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise ValueError("oauth state is invalid or expired") from exc

    if payload.get("kind") != _OAUTH_STATE_TOKEN_KIND:
        raise ValueError("oauth state kind is invalid")
    if payload.get("provider") != normalized_provider:
        raise ValueError("oauth state provider mismatch")

    redirect_to = payload.get("redirect_to")
    nonce = payload.get("nonce")
    if not isinstance(redirect_to, str) or not redirect_to:
        raise ValueError("oauth state redirect is missing")
    if not isinstance(nonce, str) or not nonce:
        raise ValueError("oauth state nonce is missing")

    return {
        "redirect_to": redirect_to,
        "nonce": nonce,
    }


def _normalize_auth_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if not normalized:
        raise ValueError("auth provider cannot be empty")
    return normalized


def _normalize_provider_user_id(provider_user_id: str) -> str:
    normalized = (provider_user_id or "").strip()
    if not normalized:
        raise ValueError("provider user id cannot be empty")
    return normalized


def _normalize_optional_identity_value(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _build_internal_username(seed: str | None) -> str:
    suffix = secrets.token_hex(_INTERNAL_USERNAME_SUFFIX_HEX_BYTES)
    normalized_seed = _normalize_optional_identity_value(seed) or _DEFAULT_INTERNAL_USERNAME_SEED
    max_prefix = max(1, 150 - (1 + len(suffix)))
    return f"{normalized_seed[:max_prefix]}_{suffix}"


def _get_auth_identity(
    db: Session,
    *,
    provider: str,
    provider_user_id: str,
) -> AuthIdentity | None:
    return (
        db.query(AuthIdentity)
        .filter(
            AuthIdentity.provider == provider,
            AuthIdentity.provider_user_id == provider_user_id,
        )
        .order_by(AuthIdentity.id.asc())
        .first()
    )


def _touch_auth_identity(
    db: Session,
    identity: AuthIdentity,
    *,
    provider_login: str | None = None,
    provider_email: str | None = None,
) -> User:
    user = identity.user
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    identity.provider_login = _normalize_optional_identity_value(provider_login) or identity.provider_login
    identity.provider_email = _normalize_optional_identity_value(provider_email) or identity.provider_email
    identity.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def _get_legacy_invite_user(
    db: Session,
    *,
    provider_user_id: str,
) -> User | None:
    return (
        db.query(User)
        .filter(User.nickname == provider_user_id)
        .order_by(User.created_at.asc(), User.id.asc())
        .first()
    )


def _repair_missing_auth_identity(
    db: Session,
    *,
    user: User,
    provider: str,
    provider_user_id: str,
    provider_login: str | None = None,
    provider_email: str | None = None,
) -> User:
    if user.id is None:
        raise RuntimeError("Auth identity repair requires a persisted user id")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    normalized_provider = _normalize_auth_provider(provider)
    normalized_provider_user_id = _normalize_provider_user_id(provider_user_id)
    normalized_provider_login = _normalize_optional_identity_value(provider_login)
    normalized_provider_email = _normalize_optional_identity_value(provider_email)
    repaired_identity = AuthIdentity(
        user_id=user.id,
        provider=normalized_provider,
        provider_user_id=normalized_provider_user_id,
        provider_login=normalized_provider_login,
        provider_email=normalized_provider_email,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(repaired_identity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_identity = _get_auth_identity(
            db,
            provider=normalized_provider,
            provider_user_id=normalized_provider_user_id,
        )
        if existing_identity is None:
            raise
        return _touch_auth_identity(
            db,
            existing_identity,
            provider_login=normalized_provider_login,
            provider_email=normalized_provider_email,
        )

    db.refresh(user)
    return user


def _raise_invite_fallback_identity_conflict(invite_provider_user_id: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "hosted_auth_invite_fallback_conflict",
            "message": (
                "Hosted OAuth signup could not reserve the matching invite login handle; "
                "the visible nickname is already owned by another user."
            ),
            "provider": AUTH_PROVIDER_INVITE,
            "provider_user_id": invite_provider_user_id,
        },
    )


def _ensure_invite_fallback_identity(
    db: Session,
    *,
    user: User,
    nickname_hint: str | None = None,
    strict: bool,
) -> bool:
    invite_provider_user_id = _normalize_optional_identity_value(user.nickname) or _normalize_optional_identity_value(
        nickname_hint
    )
    if invite_provider_user_id is None:
        if strict:
            raise RuntimeError("Hosted OAuth users require a nickname-backed invite fallback identity")
        logger.warning("Hosted user %s has no nickname-backed invite fallback identity to repair", user.id)
        return False
    if user.id is None:
        raise RuntimeError("Hosted auth fallback identities require a flushed user id")

    existing_identity = _get_auth_identity(
        db,
        provider=AUTH_PROVIDER_INVITE,
        provider_user_id=invite_provider_user_id,
    )
    if existing_identity is not None:
        if existing_identity.user_id != user.id:
            if strict:
                _raise_invite_fallback_identity_conflict(invite_provider_user_id)
            logger.warning(
                "Hosted user %s is missing invite fallback identity %r because it is owned by user %s",
                user.id,
                invite_provider_user_id,
                existing_identity.user_id,
            )
            return False
        existing_identity.provider_login = invite_provider_user_id
        return True

    db.add(
        AuthIdentity(
            user_id=user.id,
            provider=AUTH_PROVIDER_INVITE,
            provider_user_id=invite_provider_user_id,
            provider_login=invite_provider_user_id,
        )
    )
    return True


def _finish_new_hosted_user_setup(db: Session, user: User) -> None:
    record_event(db, user.id, "signup")

    try:
        from app.core.seed_demo import seed_demo_novel

        seed_demo_novel(db, user)
    except Exception:
        logger.exception("Failed to seed demo novel for user %s", user.id)


def resolve_or_provision_hosted_user_for_identity(
    db: Session,
    *,
    provider: str,
    provider_user_id: str,
    nickname: str,
    username_seed: str | None = None,
    provider_login: str | None = None,
    provider_email: str | None = None,
) -> tuple[User, bool]:
    """Resolve an existing hosted user by auth identity, or provision a new one.

    Returns ``(user, created)``. The created path preserves the current hosted
    defaults: random internal password, initial quota, signup event, and demo
    seed.
    """
    settings = get_settings()
    if settings.deploy_mode != "hosted":
        raise RuntimeError("Hosted identity provisioning is only valid in hosted mode")

    normalized_provider = _normalize_auth_provider(provider)
    normalized_provider_user_id = _normalize_provider_user_id(provider_user_id)
    resolved_nickname = _normalize_optional_identity_value(nickname)
    resolved_provider_login = _normalize_optional_identity_value(provider_login)
    resolved_provider_email = _normalize_optional_identity_value(provider_email)
    resolved_username_seed = (
        username_seed or resolved_provider_login or resolved_nickname or normalized_provider_user_id
    )
    should_attach_invite_fallback = normalized_provider != AUTH_PROVIDER_INVITE
    invite_fallback_provider_user_id = resolved_nickname if should_attach_invite_fallback else None

    with hosted_signup_lock(db):
        existing_identity = _get_auth_identity(
            db,
            provider=normalized_provider,
            provider_user_id=normalized_provider_user_id,
        )
        if existing_identity is not None:
            if should_attach_invite_fallback and existing_identity.user is not None:
                _ensure_invite_fallback_identity(
                    db,
                    user=existing_identity.user,
                    nickname_hint=invite_fallback_provider_user_id,
                    strict=False,
                )
            user = _touch_auth_identity(
                db,
                existing_identity,
                provider_login=resolved_provider_login,
                provider_email=resolved_provider_email,
            )
            return user, False

        if normalized_provider == AUTH_PROVIDER_INVITE:
            legacy_user = _get_legacy_invite_user(
                db,
                provider_user_id=normalized_provider_user_id,
            )
            if legacy_user is not None:
                logger.warning(
                    "Repairing missing hosted invite auth identity for user %s and nickname %r",
                    legacy_user.id,
                    normalized_provider_user_id,
                )
                repaired_user = _repair_missing_auth_identity(
                    db,
                    user=legacy_user,
                    provider=normalized_provider,
                    provider_user_id=normalized_provider_user_id,
                    provider_login=resolved_provider_login,
                )
                return repaired_user, False

        ensure_hosted_user_capacity(db)

        for _attempt in range(5):
            user = User(
                username=_build_internal_username(resolved_username_seed),
                nickname=resolved_nickname,
                hashed_password=hash_password(secrets.token_hex(16)),
                generation_quota=settings.initial_quota,
            )
            db.add(user)
            try:
                db.flush()
                db.add(
                    AuthIdentity(
                        user_id=user.id,
                        provider=normalized_provider,
                        provider_user_id=normalized_provider_user_id,
                        provider_login=resolved_provider_login,
                        provider_email=resolved_provider_email,
                        last_login_at=datetime.now(timezone.utc),
                    )
                )
                if should_attach_invite_fallback:
                    _ensure_invite_fallback_identity(
                        db,
                        user=user,
                        nickname_hint=invite_fallback_provider_user_id,
                        strict=True,
                    )
                db.commit()
            except IntegrityError:
                db.rollback()
                existing_identity = _get_auth_identity(
                    db,
                    provider=normalized_provider,
                    provider_user_id=normalized_provider_user_id,
                )
                if existing_identity is not None:
                    resolved_user = _touch_auth_identity(
                        db,
                        existing_identity,
                        provider_login=resolved_provider_login,
                        provider_email=resolved_provider_email,
                    )
                    return resolved_user, False
                if should_attach_invite_fallback and invite_fallback_provider_user_id is not None:
                    conflicting_invite_identity = _get_auth_identity(
                        db,
                        provider=AUTH_PROVIDER_INVITE,
                        provider_user_id=invite_fallback_provider_user_id,
                    )
                    if conflicting_invite_identity is not None:
                        _raise_invite_fallback_identity_conflict(invite_fallback_provider_user_id)
                continue

            db.refresh(user)
            _finish_new_hosted_user_setup(db, user)
            return user, True

    raise RuntimeError(
        f"Failed to provision hosted user for identity {normalized_provider}:{normalized_provider_user_id}"
    )


def _resolve_token(token: str | None, request: Request) -> str | None:
    if token:
        return token
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie_token or None


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    resolved_token = _resolve_token(token, request)
    if not resolved_token:
        raise credentials_exc

    try:
        payload = jwt.decode(resolved_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
    except jwt.PyJWTError:
        raise credentials_exc

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exc
    return user


def _get_or_create_default_user(db: Session) -> User:
    """Get or create the default selfhost user."""
    user = db.query(User).filter(User.username == "default").first()
    if user is None:
        user = User(
            username="default",
            hashed_password=hash_password("default"),
            role="admin",
            is_active=True,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.query(User).filter(User.username == "default").first()
            if user is None:
                raise
            return user
        db.refresh(user)

        # Seed demo novel on first selfhost login (best-effort).
        try:
            from app.core.seed_demo import seed_demo_novel
            seed_demo_novel(db, user)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to seed demo novel for default user")
    return user


def get_current_user_or_default(
    request: Request,
    token: str | None = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User:
    """Unified auth: selfhost auto-creates default user, hosted requires JWT."""
    settings = get_settings()

    if settings.deploy_mode == "selfhost":
        return _get_or_create_default_user(db)

    # hosted mode — token required
    resolved_token = _resolve_token(token, request)
    if not resolved_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_current_user(request=request, token=resolved_token, db=db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def _resolve_generation_billing_source(request: Request) -> str:
    return resolve_generation_billing_source(request)


def check_generation_quota(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_or_default),
) -> User:
    """Dependency stub — validates quota > 0 but does NOT decrement.

    Actual reservation / decrement happens in the endpoint or background
    workflow once the concrete billable unit is known.
    """
    ensure_ai_available(db, billing_source=_resolve_generation_billing_source(request))

    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return current_user

    if reconcile_abandoned_quota_reservations(db, user_id=current_user.id) > 0:
        try:
            db.refresh(current_user)
        except Exception:
            pass

    if current_user.generation_quota <= 0:
        _raise_quota_http_error(count=1, have=current_user.generation_quota)

    return current_user


def decrement_quota(db: Session, user: User, count: int = 1) -> None:
    """Decrement generation quota by count. Hosted mode only.

    Call this in the endpoint body after validating num_versions.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return
    if count <= 0:
        return

    result = db.execute(
        sa.update(User)
        .where(User.id == user.id, User.generation_quota >= count)
        .values(generation_quota=User.generation_quota - count)
    )
    if result.rowcount <= 0:
        db.rollback()
        # Refresh for an accurate "have N" message when the caller passes a stale User object.
        try:
            db.refresh(user)
        except Exception:
            pass
        have = getattr(user, "generation_quota", None)
        _raise_quota_http_error(count=count, have=have if isinstance(have, int) else 0)
    db.commit()
    try:
        db.refresh(user)
    except Exception:
        pass


def reconcile_abandoned_quota_reservations(db: Session, *, user_id: int | None = None) -> int:
    """Refund open reservations left behind by a dead process.

    Reservations are leased to the current process via `_QUOTA_RESERVATION_OWNER_TOKEN`.
    In the current single-process hosted architecture, any open row from another
    lease token is abandoned and safe to reconcile immediately.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return 0

    stmt = sa.select(QuotaReservation).where(
        QuotaReservation.released_at.is_(None),
        QuotaReservation.lease_token != _QUOTA_RESERVATION_OWNER_TOKEN,
    )
    if user_id is not None:
        stmt = stmt.where(QuotaReservation.user_id == user_id)

    reservations = list(db.execute(stmt).scalars())
    if not reservations:
        return 0

    refunded_by_user: dict[int, int] = {}
    released_at = datetime.now(timezone.utc)

    for reservation in reservations:
        unused = max(0, int(reservation.reserved_count) - int(reservation.charged_count))
        if unused > 0:
            refunded_by_user[reservation.user_id] = refunded_by_user.get(reservation.user_id, 0) + unused
        reservation.released_at = released_at
        reservation.updated_at = released_at

    for orphan_user_id, refunded in refunded_by_user.items():
        db.execute(
            sa.update(User)
            .where(User.id == orphan_user_id)
            .values(generation_quota=User.generation_quota + refunded)
        )

    db.commit()

    refunded_total = sum(refunded_by_user.values())
    if refunded_total > 0:
        logger.warning(
            "Recovered %s quota from abandoned reservations",
            refunded_total,
        )
    return refunded_total


def open_quota_reservation(db: Session, user_id: int, count: int = 1) -> int | None:
    """Reserve quota and create a durable reservation row in one transaction."""
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return None
    if count <= 0:
        return None

    reconcile_abandoned_quota_reservations(db, user_id=user_id)

    result = db.execute(
        sa.update(User)
        .where(User.id == user_id, User.generation_quota >= count)
        .values(generation_quota=User.generation_quota - count)
    )
    if result.rowcount <= 0:
        db.rollback()
        user = db.query(User).filter(User.id == user_id).first()
        have = getattr(user, "generation_quota", 0)
        _raise_quota_http_error(count=count, have=have)

    reservation = QuotaReservation(
        user_id=user_id,
        reserved_count=count,
        charged_count=0,
        lease_token=_QUOTA_RESERVATION_OWNER_TOKEN,
    )
    db.add(reservation)
    db.flush()
    reservation_id = int(reservation.id)
    db.commit()
    return reservation_id


def charge_quota_reservation(
    db: Session,
    reservation_id: int | None,
    n: int = 1,
    *,
    commit: bool = True,
) -> None:
    """Persist a delivered-unit charge against an open reservation."""
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return
    if reservation_id is None or n <= 0:
        return

    result = db.execute(
        sa.update(QuotaReservation)
        .where(
            QuotaReservation.id == reservation_id,
            QuotaReservation.released_at.is_(None),
            QuotaReservation.charged_count + n <= QuotaReservation.reserved_count,
        )
        .values(
            charged_count=QuotaReservation.charged_count + n,
            updated_at=sa.func.now(),
        )
    )
    if result.rowcount <= 0:
        db.rollback()
        raise RuntimeError("Failed to persist quota charge")

    if commit:
        db.commit()


def finalize_quota_reservation(
    db: Session,
    reservation_id: int | None,
    *,
    commit: bool = True,
) -> tuple[int, int]:
    """Close a durable reservation and refund any unused quota."""
    if reservation_id is None:
        return 0, 0

    reservation = (
        db.query(QuotaReservation)
        .filter(QuotaReservation.id == reservation_id)
        .first()
    )
    if not reservation or reservation.released_at is not None:
        return 0, 0

    charged = int(reservation.charged_count)
    unused = max(0, int(reservation.reserved_count) - charged)
    if unused > 0:
        db.execute(
            sa.update(User)
            .where(User.id == reservation.user_id)
            .values(generation_quota=User.generation_quota + unused)
        )

    released_at = datetime.now(timezone.utc)
    reservation.released_at = released_at
    reservation.updated_at = released_at
    if commit:
        db.commit()
    return charged, unused


def settle_quota_reservation(
    db: Session,
    reservation_id: int | None,
    *,
    charge_count: int = 0,
    commit: bool = True,
) -> tuple[int, int]:
    """Charge delivered units, then finalize the reservation."""
    if reservation_id is None:
        return 0, 0

    if charge_count > 0:
        charge_quota_reservation(db, reservation_id, n=charge_count, commit=False)
    return finalize_quota_reservation(db, reservation_id, commit=commit)


class QuotaScope:
    """Tracks how many variants were actually delivered during a generation.

    Usage::

        scope = QuotaScope(db, user_id, count=num_versions)
        scope.reserve()          # pre-deduct quota (raises 429 if insufficient)
        ...
        scope.charge(1)          # mark one variant as successfully delivered
        ...
        scope.finalize()         # refund (reserved - charged); call in finally

    Both streaming and non-streaming endpoints use the same lifecycle, ensuring
    the invariant: users only pay for variants they actually received.
    """

    def __init__(self, db: Session, user_id: int, count: int = 1):
        self.db = db
        self.user_id = user_id
        self.reserved = count
        self.charged = 0
        self._active = False
        self.reservation_id: int | None = None

    def reserve(self) -> None:
        """Pre-deduct quota and persist a reservation row."""
        self.reservation_id = open_quota_reservation(self.db, self.user_id, count=self.reserved)
        self._active = True

    def charge(self, n: int = 1) -> None:
        """Mark *n* variants as successfully delivered and persist the charge."""
        if not self._active or n <= 0:
            return

        next_total = self.charged + n
        if next_total > self.reserved:
            raise ValueError(f"Quota charge exceeds reservation: {next_total} > {self.reserved}")

        charge_quota_reservation(self.db, self.reservation_id, n=n, commit=True)
        self.charged = next_total

    def finalize(self) -> None:
        """Refund unreceived variants. Safe to call multiple times."""
        if not self._active:
            return

        if self.reservation_id is not None:
            charged, _unused = finalize_quota_reservation(self.db, self.reservation_id, commit=True)
            self.charged = charged

        self.reservation_id = None
        self._active = False


def reserve_quota(db: Session, user_id: int, count: int = 1) -> None:
    """Reserve quota by atomically decrementing `generation_quota`.

    This is intended for non-stream generation endpoints to avoid a race where:
    - generation succeeds (and writes results) and
    - quota decrement fails under concurrency (lost update / insufficient quota).

    Callers should `refund_quota()` on failure paths so users only pay for
    successful generations.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return
    if count <= 0:
        return

    reconcile_abandoned_quota_reservations(db, user_id=user_id)

    ok = try_decrement_quota(db, user_id=user_id, count=count)
    if not ok:
        user = db.query(User).filter(User.id == user_id).first()
        have = getattr(user, "generation_quota", 0)
        _raise_quota_http_error(count=count, have=have)


def refund_quota(db: Session, user_id: int, count: int = 1) -> None:
    """Refund previously reserved quota (best-effort). Hosted mode only."""
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return
    if count <= 0:
        return

    db.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(generation_quota=User.generation_quota + count)
    )
    db.commit()


def try_decrement_quota(db: Session, user_id: int, count: int = 1) -> bool:
    """Atomically decrement quota at the SQL level. Returns True on success.

    Unlike decrement_quota(), this never raises — safe to call inside
    async generators where HTTPException can't propagate cleanly.
    """
    settings = get_settings()
    if settings.deploy_mode == "selfhost":
        return True

    result = db.execute(
        sa.update(User)
        .where(User.id == user_id, User.generation_quota >= count)
        .values(generation_quota=User.generation_quota - count)
    )
    db.commit()
    return result.rowcount > 0
