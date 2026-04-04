from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.menu import Menu
from app.models.menu_category import MenuCategory
from app.models.menu_option import MenuOption
from app.models.product import Product
from app.schemas.menu import MenuCreate, MenuUpdate, MenuOptionCreate

def resolve_option_name(db: Session, opt_data: MenuOptionCreate) -> str:
    if opt_data.name:
        return opt_data.name
    if opt_data.product_id:
        product = db.query(Product).filter(Product.id == opt_data.product_id).first()
        if product:
            return product.name
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Option must have a name or a valid product_id")

def get_menus(db: Session, restaurant_id: int):
    return db.query(Menu).filter(Menu.restaurant_id == restaurant_id).all()

def get_menu(db: Session, menu_id: int):
    return db.query(Menu).filter(Menu.id == menu_id).first()

def _create_categories(db: Session, menu_id: int, categories_data: list):
    for cat_data in categories_data:
        category = MenuCategory(
            menu_id=menu_id,
            name=cat_data.name,
            max_options=cat_data.max_options,
            is_required=cat_data.is_required,
            display_order=cat_data.display_order
        )
        db.add(category)
        db.commit()
        db.refresh(category)

        for opt_data in cat_data.options:
            db.add(MenuOption(
                category_id=category.id,
                name=resolve_option_name(db, opt_data),
                additional_price=opt_data.additional_price,
                display_order=opt_data.display_order,
                product_id=opt_data.product_id
            ))
        db.commit()

def create_menu(db: Session, data: MenuCreate, restaurant_id: int):
    menu = Menu(
        restaurant_id=restaurant_id,
        name=data.name,
        price=data.price,
        is_available=data.is_available,
        available_online=data.available_online,
        available_onsite=data.available_onsite,
        image_url=data.image_url
    )
    db.add(menu)
    db.commit()
    db.refresh(menu)

    _create_categories(db, menu.id, data.categories)

    db.refresh(menu)
    return menu

def update_menu(db: Session, menu: Menu, data: MenuUpdate):
    for field, value in data.model_dump(exclude_unset=True).items():
        if field != "categories":
            setattr(menu, field, value)

    if data.categories is not None:
        db.query(MenuCategory).filter(MenuCategory.menu_id == menu.id).delete()
        db.commit()
        _create_categories(db, menu.id, data.categories)

    db.commit()
    db.refresh(menu)
    return menu

def delete_menu(db: Session, menu: Menu):
    db.delete(menu)
    db.commit()
