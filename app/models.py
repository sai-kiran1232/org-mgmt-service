from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class CreateOrgIn(BaseModel):
    organization_name: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(min_length=6)

class GetOrgIn(BaseModel):
    organization_name: str

class UpdateOrgIn(BaseModel):
    organization_name: str
    new_organization_name: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str

class DeleteOrgIn(BaseModel):
    organization_name: str

class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str

class OrgOut(BaseModel):
    id: str
    organization_name: str
    collection_name: str
    admin_email: EmailStr
    created_at: datetime
    updated_at: datetime
