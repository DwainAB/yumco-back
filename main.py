from fastapi import FastAPI
from app.routes import auth, restaurant, admin, product, menu, upload
from app.services.email_service import send_email

#Create the FastAPI application
app = FastAPI(title="Yumco API", version="1.0.0")

#register routers
app.include_router(auth.router)
app.include_router(restaurant.router)
app.include_router(admin.router)
app.include_router(product.router)
app.include_router(menu.router)
app.include_router(upload.router)

#Health check
@app.get("/")
def root():
    return {"message": "Yumco API is running"}

@app.get('/test-email')
async def test_email(email: str):
    await send_email(
        to=email,
        subject="Test Email",
        body="<h1>This is a test email</h1>"
    )
    return {"message": "Test email sent"}