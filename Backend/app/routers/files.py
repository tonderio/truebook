import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.file import UploadedFile
from app.models.process import AccountingProcess
from app.config import settings

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload/{process_id}")
async def upload_file(
    process_id: int,
    file_type: str = Form(...),  # kushki | banregio | bitso | fees
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")

    if file_type not in ("kushki", "banregio", "bitso", "fees"):
        raise HTTPException(
            status_code=400,
            detail="file_type must be 'kushki', 'banregio', 'bitso', or 'fees'",
        )

    base_dir = os.path.abspath(settings.UPLOAD_DIR)
    upload_dir = os.path.join(base_dir, str(process_id))
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1]
    stored_name = f"{file_type}_{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(upload_dir, stored_name)

    content = await file.read()
    with open(stored_path, "wb") as f:
        f.write(content)

    record = UploadedFile(
        process_id=process_id,
        file_type=file_type,
        original_name=file.filename,
        stored_path=stored_path,
        file_size=len(content),
        status="uploaded",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "original_name": record.original_name,
        "file_type": record.file_type,
        "file_size": record.file_size,
        "status": record.status,
    }


@router.get("/{process_id}")
def list_files(process_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(UploadedFile).filter(UploadedFile.process_id == process_id).all()


@router.delete("/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    if os.path.exists(record.stored_path):
        os.remove(record.stored_path)
    db.delete(record)
    db.commit()
    return {"message": "File deleted"}
