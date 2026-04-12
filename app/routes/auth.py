from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import EmailStr
from app.db.database import get_db
from app.schemas.user import UserCreate, UserResponse, UserLogin, UserUpdate
from app.services.user_service import get_user_by_email, get_user_by_id, create_user, update_user, delete_user, generate_password
from app.core.security import verify_password, create_access_token, get_current_user, hash_password
from app.models.user import User
from app.models.role import Role
from app.services.email_service import send_email

router = APIRouter(prefix="/auth", tags=["auth"])

def check_permission(current_user: User, restaurant_id: int, db: Session):
    if current_user.is_admin:
        return
    role = db.query(Role).filter(Role.user_id == current_user.id, Role.restaurant_id == restaurant_id).first()
    if not role or role.type not in ["owner", "manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

@router.post("/bootstrap-admin", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_admin(user: UserCreate, db: Session = Depends(get_db)):
    admin_exists = db.query(User).filter(User.is_admin.is_(True)).first()
    if admin_exists:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bootstrap admin is no longer available")
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bootstrap-admin only allows admin users")
    existing_user = get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return await create_user(db, user)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.is_admin:
        if not current_user.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to create admin users")
    else:
        if user.restaurant_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="restaurant_id is required for non-admin users")
        check_permission(current_user, user.restaurant_id, db)
    existing_user = get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return await create_user(db, user)

@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = get_user_by_email(db, user.email)
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(data={"sub": db_user.email})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_me(data: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return update_user(db, current_user, data, current_user)

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    delete_user(db, current_user)

@router.put("/users/{user_id}", response_model=UserResponse)
def update_user_by_id(user_id: int, data: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user_role = db.query(Role).filter(Role.user_id == user.id).first()
    if user_role:
        check_permission(current_user, user_role.restaurant_id, db)
    elif not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return update_user(db, user, data, current_user)

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_by_id(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user_role = db.query(Role).filter(Role.user_id == user.id).first()
    if user_role:
        check_permission(current_user, user_role.restaurant_id, db)
    elif not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    delete_user(db, user)

@router.post("/reset-password")
async def reset_password(email: EmailStr, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user_role = db.query(Role).filter(Role.user_id == user.id).first()
    if user_role:
        check_permission(current_user, user_role.restaurant_id, db)
    elif not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    new_password = generate_password()
    previous_hash = user.hashed_password
    user.hashed_password = hash_password(new_password)
    try:
        await send_email(
            to=user.email,
            subject="Réinitialisation de votre mot de passe Yumco",
            body=f"<h1>Bonjour {user.first_name},</h1><p>Votre nouveau mot de passe temporaire : <strong>{new_password}</strong></p>"
        )
        db.commit()
        return {"message": "Password reset and email sent successfully"}
    except Exception as exc:
        db.rollback()
        user.hashed_password = previous_hash
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Password reset failed because email could not be sent: {exc}"
        ) from exc
