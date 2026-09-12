from starlette.middleware.base import BaseHTTPMiddleware

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# 预登录与登录本身:前者签发 token,后者自行校验(见 auth.login)
_CSRF_EXEMPT_PATHS = {"/api/v1/auth/csrf"}


class CsrfMiddleware(BaseHTTPMiddleware):
    """CSRF 保护的是「浏览器自动携带凭据」的请求。

    规则:
    - Bearer 客户端不依赖 Cookie,天然免疫 CSRF,直接放行;
    - 开发环境(insecure dev)且请求没有会话 Cookie 时放行(演示旁路与预登录);
    - 其余情况——生产环境,或任何带会话 Cookie 的写请求——必须带匹配的 CSRF 头与允许的 Origin。
    """

    async def dispatch(self, request, call_next):
        if request.method.upper() in _UNSAFE_METHODS and request.url.path.startswith("/api/v1/"):
            if request.url.path not in _CSRF_EXEMPT_PATHS:
                authorization = request.headers.get("authorization", "")
                has_bearer = authorization.lower().startswith("bearer ")
                if not has_bearer:
                    from .auth import verify_csrf
                    from fastapi import HTTPException
                    from starlette.responses import JSONResponse
                    try:
                        verify_csrf(request)
                    except HTTPException as exc:
                        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response
