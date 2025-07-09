# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS: permetti al frontend (localhost:3000) di parlare col backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # URL del frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route di test
@app.get("/ping")
def ping():
    return {"message": "pong"}
