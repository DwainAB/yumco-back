from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.category import Category
from app.schemas.product import ProductCreate, ProductUpdate
from app.schemas.category import CategoryCreate, CategoryUpdate

def get_products(db: Session, restaurant_id: int):
    return db.query(Product).filter(Product.restaurant_id == restaurant_id, Product.is_deleted == False).all()

def get_product(db: Session, product_id: int):
    return db.query(Product).filter(Product.id == product_id, Product.is_deleted == False).first()

def create_product(db: Session, data: ProductCreate, restaurant_id: int):
    product = Product(**data.model_dump(), restaurant_id=restaurant_id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product

def update_product(db: Session, product: Product, data: ProductUpdate):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product

def delete_product(db: Session, product: Product):
    product.is_deleted = True
    db.commit()

def get_categories(db: Session, restaurant_id: int):
    return db.query(Category).filter(Category.restaurant_id == restaurant_id).all()

def get_category(db: Session, category_id: int):
    return db.query(Category).filter(Category.id == category_id).first()

def create_category(db: Session, data: CategoryCreate, restaurant_id: int):
    category = Category(name=data.name, kind=data.kind, restaurant_id=restaurant_id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category

def update_category(db: Session, category: Category, data: CategoryUpdate):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return category

def delete_category(db: Session, category: Category):
    db.delete(category)
    db.commit()
