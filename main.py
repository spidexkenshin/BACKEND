from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
import os
import re

app = FastAPI(title="Kenshin Anime API v5")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

MONGO_URL  = os.getenv("MONGO_URL", "")
BOT_SECRET = os.getenv("BOT_SECRET", "kenshin_secret_123")
client = AsyncIOMotorClient(MONGO_URL)
db = client["kenshin_anime_db"]

def auth(token: str):
    if token != BOT_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

def fix_id(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

class AnimeItem(BaseModel):
    title: str
    genre: str
    tag: Optional[str] = ""
    image_url: str
    tg_link: str
    trailer_url: Optional[str] = ""
    dl_link1: Optional[str] = ""
    dl_link2: Optional[str] = ""
    dl_label1: Optional[str] = "DOWNLOAD"
    dl_label2: Optional[str] = "WATCH NOW"
    seasons: Optional[str] = "1"
    episodes: Optional[str] = "12"
    year: Optional[str] = "2024"
    synopsis: Optional[str] = ""
    category: Optional[str] = "anime"
    visible: Optional[bool] = True

class UpdateItem(BaseModel):
    field: str
    value: str

class CommentItem(BaseModel):
    anime_title: str
    username: Optional[str] = "Anonymous"
    comment: str

class DemandItem(BaseModel):
    title: str
    category: Optional[str] = "anime"
    username: Optional[str] = "Anonymous"
    reason: Optional[str] = ""

class NotificationItem(BaseModel):
    message: str
    anime_title: Optional[str] = ""
    active: Optional[bool] = True
    type: Optional[str] = "info"

# ══════════ PUBLIC ══════════
@app.get("/")
async def root():
    return {"status": "✅ Kenshin Anime API v5 running!"}

@app.get("/anime")
async def get_all():
    try:
        items = await db.anime.find({"visible": True}, {"_id": 0}).to_list(5000)
        return items
    except:
        return []

@app.get("/anime/title/{title}")
async def get_by_title(title: str):
    doc = await db.anime.find_one(
        {"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}, "visible": True}, {"_id": 0}
    )
    return doc or {}

@app.get("/anime/category/{cat}")
async def get_by_cat(cat: str):
    return await db.anime.find({"category": cat, "visible": True}, {"_id": 0}).to_list(1000)

@app.get("/settings")
async def public_settings():
    doc = await db.settings.find_one({"_id": "site"}, {"_id": 0})
    return doc or {}

@app.get("/notifications")
async def get_notifs():
    return await db.notifications.find({"active": True}, {"_id": 0}).to_list(20)

@app.post("/comments/add")
async def add_comment(data: CommentItem):
    doc = data.dict()
    doc["created_at"] = datetime.utcnow().isoformat()
    r = await db.comments.insert_one(doc)
    return {"ok": True, "id": str(r.inserted_id)}

@app.get("/comments/{anime_title}")
async def get_comments(anime_title: str):
    items = await db.comments.find(
        {"anime_title": {"$regex": f"^{re.escape(anime_title)}$", "$options": "i"}},
        {"_id": 1, "username": 1, "comment": 1, "created_at": 1}
    ).to_list(100)
    return [fix_id(i) for i in items]

@app.post("/demands/add")
async def add_demand(data: DemandItem):
    doc = data.dict()
    doc["created_at"] = datetime.utcnow().isoformat()
    doc["status"] = "pending"
    doc["votes"] = 1
    # if already exists, just upvote
    ex = await db.demands.find_one({"title": {"$regex": f"^{re.escape(data.title)}$", "$options": "i"}})
    if ex:
        await db.demands.update_one({"_id": ex["_id"]}, {"$inc": {"votes": 1}})
        return {"ok": True, "msg": f"✅ Vote added for '{data.title}'!"}
    await db.demands.insert_one(doc)
    return {"ok": True, "msg": f"✅ Demand submitted for '{data.title}'!"}

@app.get("/demands/top")
async def top_demands():
    items = await db.demands.find(
        {"status": {"$ne": "rejected"}},
        {"_id": 0, "title": 1, "category": 1, "username": 1, "reason": 1, "votes": 1, "status": 1}
    ).sort("votes", -1).to_list(20)
    return items

@app.get("/stats")
async def stats():
    total = await db.anime.count_documents({"visible": True})
    manwha = await db.anime.count_documents({"category": "manwha", "visible": True})
    movies = await db.anime.count_documents({"category": "movie", "visible": True})
    return {"total": total, "manwha": manwha, "movies": movies}

# ══════════ ADMIN ══════════
@app.post("/admin/add")
async def admin_add(data: AnimeItem, token: str):
    auth(token)
    ex = await db.anime.find_one({"title": {"$regex": f"^{re.escape(data.title)}$", "$options": "i"}})
    if ex:
        return {"ok": False, "msg": f"⚠️ '{data.title}' already exists!"}
    d = data.dict()
    if not d.get("dl_link1"):
        d["dl_link1"] = d["tg_link"]
    await db.anime.insert_one(d)
    return {"ok": True, "msg": f"✅ '{data.title}' added!"}

@app.post("/admin/bulk")
async def admin_bulk(items: List[AnimeItem], token: str):
    auth(token)
    added = skipped = 0
    errors = []
    for item in items:
        try:
            ex = await db.anime.find_one({"title": {"$regex": f"^{re.escape(item.title)}$", "$options": "i"}})
            if ex:
                skipped += 1
                continue
            d = item.dict()
            if not d.get("dl_link1"):
                d["dl_link1"] = d["tg_link"]
            await db.anime.insert_one(d)
            added += 1
        except Exception as e:
            errors.append(f"{item.title}: {str(e)}")
    return {"ok": True, "added": added, "skipped": skipped, "errors": errors,
            "msg": f"✅ {added} added, {skipped} skipped"}

@app.patch("/admin/edit/{title}")
async def admin_edit(title: str, upd: UpdateItem, token: str):
    auth(token)
    r = await db.anime.update_one(
        {"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}},
        {"$set": {upd.field: upd.value}}
    )
    return {"ok": r.modified_count > 0, "msg": "✅ Updated!" if r.modified_count > 0 else "❌ Not found"}

@app.delete("/admin/delete/{title}")
async def admin_delete(title: str, token: str):
    auth(token)
    r = await db.anime.delete_one({"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}})
    return {"ok": r.deleted_count > 0, "msg": "🗑️ Deleted!" if r.deleted_count > 0 else "❌ Not found"}

@app.delete("/admin/delete-all")
async def admin_delete_all(token: str):
    auth(token)
    r = await db.anime.delete_many({})
    return {"ok": True, "msg": f"🗑️ All {r.deleted_count} anime deleted!", "count": r.deleted_count}

@app.delete("/admin/delete-category/{cat}")
async def admin_delete_cat(cat: str, token: str):
    auth(token)
    r = await db.anime.delete_many({"category": cat})
    return {"ok": True, "msg": f"🗑️ {r.deleted_count} '{cat}' deleted!"}

@app.patch("/admin/hide/{title}")
async def admin_hide(title: str, token: str):
    auth(token)
    await db.anime.update_one({"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}}, {"$set": {"visible": False}})
    return {"ok": True, "msg": "👁 Hidden!"}

@app.patch("/admin/show/{title}")
async def admin_show(title: str, token: str):
    auth(token)
    await db.anime.update_one({"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}}, {"$set": {"visible": True}})
    return {"ok": True, "msg": "✅ Visible!"}

@app.patch("/admin/move/{title}")
async def admin_move(title: str, category: str, token: str):
    auth(token)
    r = await db.anime.update_one(
        {"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}},
        {"$set": {"category": category}}
    )
    return {"ok": r.modified_count > 0, "msg": f"✅ Moved to {category}!" if r.modified_count > 0 else "❌ Not found"}

@app.get("/admin/list")
async def admin_list(token: str):
    auth(token)
    return await db.anime.find({}, {"_id": 0}).to_list(5000)

@app.patch("/admin/settings")
async def admin_settings(token: str, field: str, value: str):
    auth(token)
    await db.settings.update_one({"_id": "site"}, {"$set": {field: value}}, upsert=True)
    return {"ok": True, "msg": f"✅ '{field}' saved!"}

@app.post("/admin/notifications/push")
async def push_notification(data: NotificationItem, token: str):
    auth(token)
    doc = data.dict()
    doc["created_at"] = datetime.utcnow().isoformat()
    await db.notifications.insert_one(doc)
    return {"ok": True, "msg": "✅ Notification pushed!"}

@app.get("/admin/notifications")
async def admin_notifs(token: str):
    auth(token)
    items = await db.notifications.find({}, {"_id": 1, "message": 1, "anime_title": 1, "active": 1, "type": 1, "created_at": 1}).to_list(100)
    return [fix_id(i) for i in items]

@app.delete("/admin/notifications/{nid}")
async def del_notif(nid: str, token: str):
    auth(token)
    await db.notifications.delete_one({"_id": ObjectId(nid)})
    return {"ok": True, "msg": "🗑️ Deleted!"}

@app.patch("/admin/notifications/{nid}/toggle")
async def toggle_notif(nid: str, token: str):
    auth(token)
    doc = await db.notifications.find_one({"_id": ObjectId(nid)})
    if not doc:
        return {"ok": False, "msg": "Not found"}
    await db.notifications.update_one({"_id": ObjectId(nid)}, {"$set": {"active": not doc.get("active", True)}})
    return {"ok": True}

@app.get("/admin/comments")
async def admin_comments(token: str):
    auth(token)
    items = await db.comments.find({}, {"_id": 1, "anime_title": 1, "username": 1, "comment": 1, "created_at": 1}).to_list(500)
    return [fix_id(i) for i in items]

@app.delete("/admin/comments/{cid}")
async def del_comment(cid: str, token: str):
    auth(token)
    await db.comments.delete_one({"_id": ObjectId(cid)})
    return {"ok": True, "msg": "🗑️ Deleted!"}

@app.get("/admin/demands")
async def admin_demands(token: str):
    auth(token)
    items = await db.demands.find({}, {"_id": 1, "title": 1, "category": 1, "username": 1, "reason": 1, "votes": 1, "status": 1, "created_at": 1}).to_list(500)
    return [fix_id(i) for i in items]

@app.patch("/admin/demands/{did}")
async def update_demand(did: str, status: str, token: str):
    auth(token)
    await db.demands.update_one({"_id": ObjectId(did)}, {"$set": {"status": status}})
    return {"ok": True, "msg": f"✅ Status: {status}"}

@app.delete("/admin/demands/{did}")
async def del_demand(did: str, token: str):
    auth(token)
    await db.demands.delete_one({"_id": ObjectId(did)})
    return {"ok": True, "msg": "🗑️ Deleted!"}
