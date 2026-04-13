from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.agent_templates import router as agent_templates_router
from backend.api.routes.chat_sessions import router as chat_sessions_router
from backend.api.routes.documents import router as documents_router
from backend.api.routes.jobs import router as jobs_router
from backend.api.routes.runtime_config import router as runtime_config_router
from backend.api.routes.traces import router as traces_router
from backend.api.errors import ApiException, api_exception_handler
from backend.api.ws_handler import ws_router


app = FastAPI(title="OpenAgent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ApiException, api_exception_handler)

app.include_router(agent_templates_router)
app.include_router(chat_sessions_router)
app.include_router(documents_router)
app.include_router(jobs_router)
app.include_router(runtime_config_router)
app.include_router(traces_router)
app.include_router(ws_router)

