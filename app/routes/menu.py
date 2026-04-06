from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schemas.menu import MenuCreate, MenuUpdate, MenuResponse
from app.services.menu_service import get_menus, get_menu, create_menu, update_menu, delete_menu
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/restaurants", tags=["menus"])

@router.get("/{restaurant_id}/menus", response_model=list[MenuResponse])
def list_menus(restaurant_id: int, db: Session = Depends(get_db)):
    return get_menus(db, restaurant_id)

@router.get("/{restaurant_id}/menus/{menu_id}", response_model=MenuResponse)
def get_one_menu(restaurant_id: int, menu_id: int, db: Session = Depends(get_db)):
    menu = get_menu(db, menu_id)
    if not menu or menu.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    return menu

@router.post("/{restaurant_id}/menus", response_model=MenuResponse, status_code=status.HTTP_201_CREATED)
def add_menu(restaurant_id: int, data: MenuCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_menu(db, data, restaurant_id)

@router.put("/{restaurant_id}/menus/{menu_id}", response_model=MenuResponse)
def edit_menu(restaurant_id: int, menu_id: int, data: MenuUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    menu = get_menu(db, menu_id)
    if not menu or menu.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    return update_menu(db, menu, data)

@router.delete("/{restaurant_id}/menus/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_menu(restaurant_id: int, menu_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    menu = get_menu(db, menu_id)
    if not menu or menu.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    delete_menu(db, menu)
