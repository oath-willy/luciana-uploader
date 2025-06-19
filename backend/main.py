from fastapi import FastAPI
from api.routes import router

app = FastAPI(title="Luciana Backend API")

app.include_router(router)
