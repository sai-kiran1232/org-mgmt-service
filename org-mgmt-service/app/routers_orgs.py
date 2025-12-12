from fastapi import APIRouter, Depends, HTTPException, status
from .models import CreateOrgIn, GetOrgIn, UpdateOrgIn, DeleteOrgIn, OrgOut, AdminLoginIn
from .database import get_master_db
from .auth import hash_password, verify_password, create_access_token
from .deps import get_current_admin
from datetime import datetime, timezone
from bson import ObjectId
from typing import Any

router = APIRouter(prefix="/org", tags=["organizations"])

def org_collection_name(name: str) -> str:
    return f"org_{name.lower()}"

async def ensure_indexes(db):
    await db["organizations"].create_index("organization_name", unique=True)
    await db["admins"].create_index("email", unique=True)
    await db["admins"].create_index([("org_id", 1)])

@router.post("/create")
async def create_org(payload: CreateOrgIn):
    db = await get_master_db()
    await ensure_indexes(db)

    ocol = db["organizations"]
    acol = db["admins"]

    # Check uniqueness
    exists = await ocol.find_one({"organization_name": payload.organization_name.lower()})
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization already exists")

    # Create org metadata
    coll_name = org_collection_name(payload.organization_name)
    now = datetime.now(timezone.utc)
    org_doc = {
        "organization_name": payload.organization_name.lower(),
        "collection_name": coll_name,
        "created_at": now,
        "updated_at": now,
    }
    res = await ocol.insert_one(org_doc)
    org_id = res.inserted_id

    # Create org-specific collection (empty doc to ensure creation)
    await db[coll_name].insert_one({"_seed": True})
    await db[coll_name].delete_one({"_seed": True})

    # Create admin
    admin_doc = {
        "org_id": org_id,
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "created_at": now,
        "updated_at": now,
        "is_super_admin": True,
    }
    try:
        await acol.insert_one(admin_doc)
    except Exception as e:
        # rollback org
        await ocol.delete_one({"_id": org_id})
        await db.drop_collection(coll_name)
        raise HTTPException(status_code=400, detail=f"Failed to create admin: {str(e)}")

    out = {
        "id": str(org_id),
        "organization_name": org_doc["organization_name"],
        "collection_name": coll_name,
        "admin_email": payload.email.lower(),
        "created_at": now,
        "updated_at": now,
    }
    return out

@router.get("/get", response_model=OrgOut)
async def get_org(organization_name: str):
    db = await get_master_db()
    doc = await db["organizations"].find_one({"organization_name": organization_name.lower()})
    if not doc:
        raise HTTPException(status_code=404, detail="Organization not found")
    # Find admin email for convenience (first admin)
    adm = await db["admins"].find_one({"org_id": doc["_id"]})
    return {
        "id": str(doc["_id"]),
        "organization_name": doc["organization_name"],
        "collection_name": doc["collection_name"],
        "admin_email": adm["email"] if adm else "unknown",
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }

@router.put("/update")
async def update_org(payload: UpdateOrgIn, admin=Depends(get_current_admin)):
    # Only allow if the token belongs to this org admin (email + org_id must match)
    if admin.get("email") != payload.email.lower():
        raise HTTPException(status_code=403, detail="Not your account")
    db = await get_master_db()
    ocol = db["organizations"]
    # Get current org
    cur = await ocol.find_one({"organization_name": payload.organization_name.lower()})
    if not cur:
        raise HTTPException(status_code=404, detail="Organization not found")
    if str(cur["_id"]) != admin.get("org_id"):
        raise HTTPException(status_code=403, detail="You are not admin of this organization")

    # Validate credentials
    adm = await db["admins"].find_one({"org_id": cur["_id"], "email": payload.email.lower()})
    if not adm:
        raise HTTPException(status_code=401, detail="Admin not found")
    if not verify_password(payload.password, adm["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check if new name already exists
    if payload.new_organization_name.lower() != cur["organization_name"]:
        exist_new = await ocol.find_one({"organization_name": payload.new_organization_name.lower()})
        if exist_new:
            raise HTTPException(status_code=409, detail="New organization name already exists")

    # Migrate collection (copy documents)
    old_coll = cur["collection_name"]
    new_coll = old_coll if payload.new_organization_name.lower() == cur["organization_name"] else f"org_{payload.new_organization_name.lower()}"
    if new_coll != old_coll:
        # Copy all docs
        src = db[old_coll]
        dst = db[new_coll]
        async for doc in src.find():
            _doc = dict(doc)
            _doc.pop("_id", None)
            await dst.insert_one(_doc)
        # Drop old
        await db.drop_collection(old_coll)

    # Update org metadata
    now = datetime.now(datetime.now().astimezone().tzinfo)
    await ocol.update_one(
        {"_id": cur["_id"]},
        {"$set": {
            "organization_name": payload.new_organization_name.lower(),
            "collection_name": new_coll,
            "updated_at": datetime.now(datetime.utcnow().astimezone().tzinfo)
        }}
    )
    return {"message": "Organization updated", "collection_name": new_coll}

@router.delete("/delete")
async def delete_org(payload: DeleteOrgIn, admin=Depends(get_current_admin)):
    db = await get_master_db()
    ocol = db["organizations"]
    cur = await ocol.find_one({"organization_name": payload.organization_name.lower()})
    if not cur:
        raise HTTPException(status_code=404, detail="Organization not found")
    if str(cur["_id"]) != admin.get("org_id"):
        raise HTTPException(status_code=403, detail="Not authorized to delete this organization")

    # Delete admins and collection
    await db["admins"].delete_many({"org_id": cur["_id"]})
    await db.drop_collection(cur["collection_name"])
    await ocol.delete_one({"_id": cur["_id"]})
    return {"message": "Organization deleted"}

# -------- Admin auth routes --------
auth_router = APIRouter(prefix="/admin", tags=["auth"])

@auth_router.post("/login")
async def admin_login(payload: AdminLoginIn):
    db = await get_master_db()
    adm = await db["admins"].find_one({"email": payload.email.lower()})
    if not adm:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, adm["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Fetch org
    org = await db["organizations"].find_one({"_id": adm["org_id"]})
    token = create_access_token({"email": adm["email"], "org_id": str(org["_id"])})
    return {"access_token": token, "token_type": "bearer", "org_id": str(org["_id"]), "organization_name": org["organization_name"]}
