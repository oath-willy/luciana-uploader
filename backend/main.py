from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as upload_router  # o `from routes import ...` se non usi sottocartella
import os

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Test
@app.get("/ping")
def ping():
    return {"message": "pong"}

# Registra rotte
app.include_router(upload_router)

# ✅ Avvio solo quando eseguito direttamente (es. da Docker o Azure App Service)
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
