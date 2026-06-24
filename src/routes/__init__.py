"""路由模块"""
from .health import router as health_router
from .requirement import router as requirement_router
from .task import router as task_router
from .agent import router as agent_router
from .itinerary import router as itinerary_router
from .validate import router as validate_router
from .static_data import router as static_data_router
from .integration import router as integration_router
from .nlp import router as nlp_router
from .weather import router as weather_router
from .navigation import router as navigation_router
from .auth import router as auth_router
from .ws import router as ws_router
from .itinerary_phase4 import router as itinerary_phase4_router
from .qweather import router as qweather_router
__all__ = [
    "health_router", "requirement_router", "task_router", 
    "agent_router", "itinerary_router", "validate_router", "static_data_router", 
    "integration_router", "nlp_router", "weather_router", "navigation_router", "auth_router",
    "ws_router", "itinerary_phase4_router", "qweather_router"
]