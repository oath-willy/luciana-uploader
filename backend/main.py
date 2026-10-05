from dotenv import load_dotenv
load_dotenv()

import os
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.routes import router
from api import control_panel
from api import mc_code
from api import pdb_settings
from api import items_code
from api import pdb_brands
from api import pdb_mc_classification
from api import fast_track
from api.db import products
from api.db import countries_dictionary
from api.db import database_tables
from services.app_auth import AppAuthorizationMiddleware, in_cloud

app = FastAPI(docs_url=None if in_cloud() else "/docs",
              redoc_url=None if in_cloud() else "/redoc",
              openapi_url=None if in_cloud() else "/openapi.json")
app.add_middleware(AppAuthorizationMiddleware)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin] if in_cloud() else [frontend_origin, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Healthcheck
@app.get("/ping")
def ping():
    return {"message": "Hello!"}

# Include i router DOPO la creazione dell'app
app.include_router(products.router, prefix="/api")
app.include_router(countries_dictionary.router, prefix="/api")
app.include_router(database_tables.router, prefix="/api")
app.include_router(mc_code.router, prefix="/api")
app.include_router(mc_code.legacy_router, prefix="/api")
app.include_router(pdb_settings.router, prefix="/api")
app.include_router(items_code.router, prefix="/api")
app.include_router(pdb_brands.router, prefix="/api")
app.include_router(pdb_mc_classification.router, prefix="/api")
app.include_router(fast_track.router, prefix="/api")
app.include_router(router, prefix="/api")
app.include_router(control_panel.router, prefix="/api")

# Solo in sviluppo
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
