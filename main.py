from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, restaurant, admin, product, menu, upload, all_you_can_eat, table, reservation, customer, order, revenue, performance, customer_analytics, subscription, ai, stripe_connect, hubrise
from app.services.email_service import send_email

#Create the FastAPI application
app = FastAPI(title="Yumco API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#register routers
app.include_router(auth.router)
app.include_router(restaurant.router)
app.include_router(admin.router)
app.include_router(product.router)
app.include_router(menu.router)
app.include_router(upload.router)
app.include_router(all_you_can_eat.router)
app.include_router(table.router)
app.include_router(reservation.router)
app.include_router(order.router)
app.include_router(revenue.router)
app.include_router(performance.router)
app.include_router(customer_analytics.router)
app.include_router(customer.router)
app.include_router(subscription.router)
app.include_router(ai.router)
app.include_router(stripe_connect.router)
app.include_router(hubrise.router)

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
