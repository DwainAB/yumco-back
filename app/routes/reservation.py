from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.reservation import Reservation
from app.schemas.reservation import ReservationCreate, ReservationUpdate, ReservationResponse
from app.core.security import get_current_user
from app.models.user import User
from app.services.notification_service import notify_new_reservation

router = APIRouter(prefix="/restaurants", tags=["reservations"])

@router.get("/{restaurant_id}/reservations", response_model=list[ReservationResponse])
def list_reservations(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Reservation).filter(Reservation.restaurant_id == restaurant_id).all()

@router.get("/{restaurant_id}/reservations/{reservation_id}", response_model=ReservationResponse)
def get_reservation(restaurant_id: int, reservation_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id, Reservation.restaurant_id == restaurant_id).first()
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    return reservation

@router.post("/{restaurant_id}/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(restaurant_id: int, data: ReservationCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    reservation = Reservation(restaurant_id=restaurant_id, **data.model_dump())
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    background_tasks.add_task(
        notify_new_reservation,
        restaurant_id,
        reservation.full_name,
        reservation.number_of_people,
        str(reservation.reservation_date),
        str(reservation.reservation_time)[:5],
    )
    return reservation

@router.put("/{restaurant_id}/reservations/{reservation_id}", response_model=ReservationResponse)
@router.patch("/{restaurant_id}/reservations/{reservation_id}", response_model=ReservationResponse)
def update_reservation(restaurant_id: int, reservation_id: int, data: ReservationUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id, Reservation.restaurant_id == restaurant_id).first()
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(reservation, field, value)
    db.commit()
    db.refresh(reservation)
    return reservation

@router.delete("/{restaurant_id}/reservations/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservation(restaurant_id: int, reservation_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    reservation = db.query(Reservation).filter(Reservation.id == reservation_id, Reservation.restaurant_id == restaurant_id).first()
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    db.delete(reservation)
    db.commit()
