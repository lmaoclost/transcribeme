"""Controllers (MVC): one APIRouter per resource. Wired by app.api.create_app."""

from app.routers import batches, health, jobs, legacy, preview, settings, uploads

__all__ = ["batches", "health", "jobs", "legacy", "preview", "settings", "uploads"]
