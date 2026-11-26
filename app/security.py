from typing import Annotated
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User

hasher = PasswordHasher()
basic = HTTPBasic()
dummy_hash = hasher.hash("not-a-real-password")

def current_user(credentials: Annotated[HTTPBasicCredentials, Depends(basic)], db: Annotated[Session, Depends(get_db)]):
    user = db.scalar(select(User).where(User.username == credentials.username))
    try:
        valid = hasher.verify(user.password_hash if user else dummy_hash, credentials.password)
    except VerificationError:
        valid = False
    if not user or not valid:
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return user

def admin_user(user: Annotated[User, Depends(current_user)]):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user