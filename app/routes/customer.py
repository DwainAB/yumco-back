from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/restaurants", tags=["customers"])

@router.get("/{restaurant_id}/customers", response_model=list[CustomerResponse])
def list_customers(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Customer).filter(Customer.restaurant_id == restaurant_id).all()

@router.get("/{restaurant_id}/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(restaurant_id: int, customer_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.restaurant_id == restaurant_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer

@router.put("/{restaurant_id}/customers/{customer_id}", response_model=CustomerResponse)
def update_customer(restaurant_id: int, customer_id: int, data: CustomerUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.restaurant_id == restaurant_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer

@router.delete("/{restaurant_id}/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(restaurant_id: int, customer_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.restaurant_id == restaurant_id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    db.delete(customer)
    db.commit()
