def make_middlewares():
    from fastapi.middleware import Middleware
    from fastapi.middleware.cors import CORSMiddleware

    from coder.middleware.middlewares import BackGroundTaskMiddleware, TraceMiddleware, UseTimeMiddleware
    from coder.settings import settings

    middleware = [
        Middleware(BackGroundTaskMiddleware),
        Middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origin_patterns,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=settings.cors_allowed_methods,
            allow_headers=settings.cors_allowed_headers,
            max_age=settings.cors_max_age,
            expose_headers=settings.cors_expose_headers,
        ),
        Middleware(TraceMiddleware),
        Middleware(UseTimeMiddleware),
    ]

    return middleware
