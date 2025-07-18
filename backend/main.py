import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
print("🔐 AZURE_STORAGE_CONNECTION_STRING =", os.getenv("AZURE_STORAGE_CONNECTION_STRING"))


app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],  # <-- ora valore esplicito
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
def ping():
    return {"message": "stong"}

# Include tutte le rotte
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
