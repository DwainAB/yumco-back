from fastapi import FastAPI
from app.routes import auth

#Create the FastAPI application
app = FastAPI(title="Yumco API", version="1.0.0")

#register routers
app.include_router(auth.router)

#Health check
@app.get("/")
def root():
    return {"message": "Yumco API is running"}