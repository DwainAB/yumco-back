from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.all_you_can_eat import AllYouCanEat
from app.schemas.all_you_can_eat import AllYouCanEatCreate, AllYouCanEatUpdate, AllYouCanEatResponse
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/restaurants", tags=["all-you-can-eat"])

@router.get("/{restaurant_id}/all-you-can-eat", response_model=list[AllYouCanEatResponse])
def list_offers(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(AllYouCanEat).filter(AllYouCanEat.restaurant_id == restaurant_id).all()

@router.post("/{restaurant_id}/all-you-can-eat", response_model=AllYouCanEatResponse, status_code=status.HTTP_201_CREATED)
def create_offer(restaurant_id: int, data: AllYouCanEatCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = AllYouCanEat(restaurant_id=restaurant_id, name=data.name, price=data.price)
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer

@router.put("/{restaurant_id}/all-you-can-eat/{offer_id}", response_model=AllYouCanEatResponse)
def update_offer(restaurant_id: int, offer_id: int, data: AllYouCanEatUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = db.query(AllYouCanEat).filter(AllYouCanEat.id == offer_id, AllYouCanEat.restaurant_id == restaurant_id).first()
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(offer, field, value)
    db.commit()
    db.refresh(offer)
    return offer

@router.delete("/{restaurant_id}/all-you-can-eat/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(restaurant_id: int, offer_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = db.query(AllYouCanEat).filter(AllYouCanEat.id == offer_id, AllYouCanEat.restaurant_id == restaurant_id).first()
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    db.delete(offer)
    db.commit()
