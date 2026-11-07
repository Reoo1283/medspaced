from fastapi import APIRouter

from app.api import (
    routes_auth,
    routes_content,
    routes_exam,
    routes_exercises,
    routes_review,
    routes_skills,
    routes_study,
)

api_router = APIRouter()
api_router.include_router(routes_auth.router)
api_router.include_router(routes_content.router)
api_router.include_router(routes_skills.router)
api_router.include_router(routes_exercises.router)
api_router.include_router(routes_review.router)
api_router.include_router(routes_study.router)
api_router.include_router(routes_exam.router)
