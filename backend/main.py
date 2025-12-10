import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from dotenv import load_dotenv

from api.routes import router
from api import run_script
from api import run_script_log
from backend.api.db import products

load_dotenv()

app = FastAPI()

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
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
app.include_router(router, prefix="/api")
app.include_router(run_script.router, prefix="/api")
app.include_router(run_script_log.router, prefix="/api")

# Solo in sviluppo
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
