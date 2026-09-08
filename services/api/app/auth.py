"""Small in-memory authentication provider for the demo API.

The token store is deliberately replaceable; production deployments should
provide a database/OIDC-backed implementation instead.
"""
from secrets import token_urlsafe
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
_tokens: dict[str, dict] = {}
_USERS = {
    "demo": {"id": "demo-user", "email": "demo@voicelens.local", "name": "Demo Analyst", "password": "demo", "role": "ANALYST"},
    "viewer": {"id": "viewer-user", "email": "viewer@voicelens.local", "name": "Demo Viewer", "password": "viewer", "role": "VIEWER"},
}

class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)

def _public(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}

def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer" or credentials.credentials not in _tokens:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "unauthorized"}, headers={"WWW-Authenticate": "Bearer"})
    return _tokens[credentials.credentials]

@router.post("/login")
def login(request: LoginRequest):
    user = _USERS.get(request.username)
    if not user or request.password != user["password"]:
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials"}, headers={"WWW-Authenticate": "Bearer"})
    token = token_urlsafe(32)
    session = _public(user) | {"projects": [{"project_id": "demo-project", "role": user["role"], "permissions": ["read", "analyze"] if user["role"] != "VIEWER" else ["read"]}]}
    _tokens[token] = session
    return {"access_token": token, "token_type": "bearer", "user": session}

@router.get("/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return user

@router.post("/logout", status_code=204)
def logout(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials:
        _tokens.pop(credentials.credentials, None)
