from fastapi import APIRouter, Depends, UploadFile, File
from app.core.security import get_current_user
from app.models.user import User
from app.services.cloudinary_service import upload_image

router = APIRouter(prefix="/upload", tags=["upload"])

@router.post("")
async def upload(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    url = upload_image(await file.read())
    return {"url": url}
