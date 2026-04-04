import cloudinary
import cloudinary.uploader
from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)

def upload_image(file) -> str:
    result = cloudinary.uploader.upload(file, folder="yumco/products")
    return result["secure_url"]

def delete_image(public_id: str):
    cloudinary.uploader.destroy(public_id)
