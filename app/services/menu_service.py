from sqlalchemy.orm import Session
from app.models.menu import Menu
from app.models.menu_category import MenuCategory
from app.models.menu_option import MenuOption
from app.schemas.menu import MenuCreate, MenuUpdate

def get_menus(db: Session, restaurant_id: int):
    return db.query(Menu).filter(Menu.restaurant_id == restaurant_id).all()

def get_menu(db: Session, menu_id: int):
    return db.query(Menu).filter(Menu.id == menu_id).first()

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

    for cat_data in data.categories:
        category = MenuCategory(
            menu_id=menu.id,
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
                name=opt_data.name,
                additional_price=opt_data.additional_price,
                display_order=opt_data.display_order,
                product_id=opt_data.product_id
            ))
        db.commit()

    db.refresh(menu)
    return menu

def update_menu(db: Session, menu: Menu, data: MenuUpdate):
    for field, value in data.model_dump(exclude_unset=True).items():
        if field != "categories":
            setattr(menu, field, value)

    if data.categories is not None:
        db.query(MenuCategory).filter(MenuCategory.menu_id == menu.id).delete()
        for cat_data in data.categories:
            category = MenuCategory(
                menu_id=menu.id,
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
                    name=opt_data.name,
                    additional_price=opt_data.additional_price,
                    display_order=opt_data.display_order,
                    product_id=opt_data.product_id
                ))
        db.commit()

    db.commit()
    db.refresh(menu)
    return menu

def delete_menu(db: Session, menu: Menu):
    db.delete(menu)
    db.commit()
