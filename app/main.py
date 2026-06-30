import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.auth import auth_router, user_router
from app.api.v1.body_profiles import router as body_profiles_router
from app.api.v1.care import router as care_router
from app.api.v1.community import router as community_router
from app.api.v1.credits import router as credits_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.items import router as items_router
from app.api.v1.membership import router as membership_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.orders import router as orders_router
from app.api.v1.outfits import collections_router, outfits_router
from app.api.v1.promo_codes import router as promo_codes_router
from app.api.v1.purchase_preview import router as purchase_preview_router
from app.api.v1.puzzle import router as puzzle_router
from app.api.v1.referral import router as referral_router
from app.api.v1.sign_in import router as sign_in_router
from app.api.v1.statistics import router as statistics_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.tryon import router as tryon_router
from app.api.v1.upload import router as upload_router
from app.api.v1.users import router as users_router
from app.api.v1.wear_history import router as wear_history_router
from app.core.config import settings
from app.core.exceptions import AppException, app_exception_handler
from app.core.responses import success


def create_app() -> FastAPI:
    app = FastAPI(
        title="数字衣橱后端 API",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    cors_origins = (
        [origin.strip() for origin in settings.cors_origins.split(",")]
        if settings.cors_origins
        else []
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppException, app_exception_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": 1001,
                "message": f"参数错误: {exc.errors()[0]['msg'] if exc.errors() else '未知'}",
                "data": None,
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logging.error(
            "Unhandled exception at %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=settings.debug,
        )
        if settings.debug:
            message = f"服务器内部错误: {exc}"
            data = {"traceback": traceback.format_exc()}
        else:
            message = "服务器内部错误"
            data = None
        return JSONResponse(
            status_code=500,
            content={"code": 9999, "message": message, "data": data},
        )

    app.include_router(auth_router, prefix="/v1")
    app.include_router(user_router, prefix="/v1")
    app.include_router(items_router, prefix="/v1")
    app.include_router(outfits_router, prefix="/v1")
    app.include_router(collections_router, prefix="/v1")
    app.include_router(body_profiles_router, prefix="/v1")
    app.include_router(wear_history_router, prefix="/v1")
    app.include_router(care_router, prefix="/v1")
    app.include_router(statistics_router, prefix="/v1")
    app.include_router(tasks_router, prefix="/v1")
    app.include_router(purchase_preview_router, prefix="/v1")
    app.include_router(tryon_router, prefix="/v1")
    app.include_router(membership_router, prefix="/v1")
    app.include_router(credits_router, prefix="/v1")
    app.include_router(sign_in_router, prefix="/v1")
    app.include_router(puzzle_router, prefix="/v1")
    app.include_router(notifications_router, prefix="/v1")
    app.include_router(orders_router, prefix="/v1")
    app.include_router(promo_codes_router, prefix="/v1")
    app.include_router(referral_router, prefix="/v1")
    app.include_router(community_router, prefix="/v1")
    app.include_router(favorites_router, prefix="/v1")
    app.include_router(users_router, prefix="/v1")
    app.include_router(upload_router, prefix="/v1")

    @app.get("/health")
    async def health():
        return success(data={"status": "ok"})

    return app


app = create_app()
