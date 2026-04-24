from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from decimal import Decimal
from app.db.database import get_db
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.product_service import get_products, get_product, create_product, update_product, delete_product, get_categories, get_category, create_category, update_category, delete_category
from app.services.recommendation_service import get_product_recommendations
from app.services.cloudinary_service import upload_image
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/restaurants", tags=["products"])

@router.get("/{restaurant_id}/categories", response_model=list[CategoryResponse])
def list_categories(restaurant_id: int, db: Session = Depends(get_db)):
    return get_categories(db, restaurant_id)

@router.post("/{restaurant_id}/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def add_category(restaurant_id: int, data: CategoryCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_category(db, data, restaurant_id)

@router.put("/{restaurant_id}/categories/{category_id}", response_model=CategoryResponse)
def edit_category(restaurant_id: int, category_id: int, data: CategoryUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = get_category(db, category_id)
    if not category or category.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return update_category(db, category, data)

@router.delete("/{restaurant_id}/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_category(restaurant_id: int, category_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = get_category(db, category_id)
    if not category or category.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    delete_category(db, category)

@router.get("/{restaurant_id}/products", response_model=list[ProductResponse])
def list_products(restaurant_id: int, db: Session = Depends(get_db)):
    return get_products(db, restaurant_id)

@router.post("/{restaurant_id}/products/recommendations", response_model=RecommendationResponse)
def recommend_products(restaurant_id: int, data: RecommendationRequest, db: Session = Depends(get_db)):
    try:
        return get_product_recommendations(db, restaurant_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

@router.get("/{restaurant_id}/products/{product_id}", response_model=ProductResponse)
def get_one_product(restaurant_id: int, product_id: int, db: Session = Depends(get_db)):
    product = get_product(db, product_id)
    if not product or product.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product

@router.post("/{restaurant_id}/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def add_product(
    restaurant_id: int,
    name: str = Form(...),
    price: Decimal = Form(...),
    description: str | None = Form(None),
    category_id: int | None = Form(None),
    is_available: bool = Form(True),
    available_online: bool = Form(True),
    available_onsite: bool = Form(True),
    group: str | None = Form(None),
    allergens: list[str] = Form([]),
    image: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    image_url = None
    if image:
        image_url = upload_image(await image.read())

    data = ProductCreate(
        name=name,
        price=price,
        description=description,
        category_id=category_id,
        is_available=is_available,
        available_online=available_online,
        available_onsite=available_onsite,
        group=group,
        allergens=allergens,
        image_url=image_url
    )
    return create_product(db, data, restaurant_id)

@router.put("/{restaurant_id}/products/{product_id}", response_model=ProductResponse)
async def edit_product(
    restaurant_id: int,
    product_id: int,
    name: str | None = Form(None),
    price: Decimal | None = Form(None),
    description: str | None = Form(None),
    category_id: int | None = Form(None),
    is_available: bool | None = Form(None),
    available_online: bool | None = Form(None),
    available_onsite: bool | None = Form(None),
    group: str | None = Form(None),
    allergens: list[str] | None = Form(None),
    image: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    product = get_product(db, product_id)
    if not product or product.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    fields = {
        "name": name,
        "price": price,
        "description": description,
        "category_id": category_id,
        "is_available": is_available,
        "available_online": available_online,
        "available_onsite": available_onsite,
        "group": group,
        "allergens": allergens,
    }
    if image:
        fields["image_url"] = upload_image(await image.read())

    data = ProductUpdate(**{k: v for k, v in fields.items() if v is not None})
    return update_product(db, product, data)

@router.delete("/{restaurant_id}/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_product(restaurant_id: int, product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = get_product(db, product_id)
    if not product or product.restaurant_id != restaurant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    delete_product(db, product)
