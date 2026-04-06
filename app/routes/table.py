from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.table import Table
from app.models.restaurant import Restaurant
from app.schemas.table import TableCreate, TableUpdate, TableResponse
from app.core.security import get_current_user
from app.models.user import User
from app.services.receipt_service import generate_table_ticket

router = APIRouter(prefix="/restaurants", tags=["tables"])

@router.get("/{restaurant_id}/tables", response_model=list[TableResponse])
def list_tables(restaurant_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Table).filter(Table.restaurant_id == restaurant_id).all()

@router.get("/{restaurant_id}/tables/{table_id}", response_model=TableResponse)
def get_table(restaurant_id: int, table_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    table = db.query(Table).filter(Table.id == table_id, Table.restaurant_id == restaurant_id).first()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    return table

@router.post("/{restaurant_id}/tables", response_model=TableResponse, status_code=status.HTTP_201_CREATED)
def create_table(restaurant_id: int, data: TableCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    table = Table(restaurant_id=restaurant_id, **data.model_dump())
    db.add(table)
    db.commit()
    db.refresh(table)
    return table

@router.put("/{restaurant_id}/tables/{table_id}", response_model=TableResponse)
def update_table(restaurant_id: int, table_id: int, data: TableUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    table = db.query(Table).filter(Table.id == table_id, Table.restaurant_id == restaurant_id).first()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(table, field, value)
    db.commit()
    db.refresh(table)
    return table

@router.get("/{restaurant_id}/tables/{table_id}/ticket")
def get_table_ticket(restaurant_id: int, table_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    table = db.query(Table).filter(Table.id == table_id, Table.restaurant_id == restaurant_id).first()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    restaurant = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    pdf = generate_table_ticket(table, restaurant)
    filename = f"table_{table.table_number}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={filename}"})


@router.delete("/{restaurant_id}/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(restaurant_id: int, table_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    table = db.query(Table).filter(Table.id == table_id, Table.restaurant_id == restaurant_id).first()
    if not table:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Table not found")
    db.delete(table)
    db.commit()
