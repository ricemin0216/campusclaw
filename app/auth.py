"""JWT Bearer token issuance and validation."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import jwt


TOKEN_LIFETIME_SECONDS = 60 * 60


class TokenValidationError(ValueError):
    """Raised when an Authorization token cannot authenticate a request."""


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_in: int


class JwtService:
    def __init__(self, secret: str, now: Callable[[], int] | None = None) -> None:
        self.secret = secret
        self.now = now or (lambda: int(time.time()))

    def issue(self, user_id: int) -> AccessToken:
        issued_at = self.now()
        claims = {
            "sub": str(user_id),
            "iat": issued_at,
            "exp": issued_at + TOKEN_LIFETIME_SECONDS,
            "jti": str(uuid.uuid4()),
        }
        return AccessToken(
            value=jwt.encode(claims, self.secret, algorithm="HS256"),
            expires_in=TOKEN_LIFETIME_SECONDS,
        )

    def decode(self, token: str) -> dict[str, Any]:
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                options={"require": ["sub", "iat", "exp", "jti"]},
            )
        except jwt.PyJWTError as error:
            raise TokenValidationError("invalid bearer token") from error
        if not isinstance(claims.get("sub"), str) or not claims["sub"].isdigit() or int(claims["sub"]) <= 0:
            raise TokenValidationError("invalid bearer token")
        if not isinstance(claims.get("jti"), str) or not claims["jti"]:
            raise TokenValidationError("invalid bearer token")
        return claims
