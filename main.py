from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import os

app = FastAPI(title="Kenshin Anime API v4")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

MONGO_URL  = os.getenv("MONGO_URL", "")
BOT_SECRET = os.getenv("BOT_SECRET", "kenshin_secret_123")
client = AsyncIOMotorClient(MONGO_URL)
db = client["kenshin_anime_db"]

class AnimeItem(BaseModel):
    title: str
    genre: str
    tag: Optional[str] = ""
    image_url: str
    tg_link: str
    dl_link1: Optional[str] = ""
    dl_link2: Optional[str] = ""
    dl_label1: Optional[str] = "DOWNLOAD"
    dl_label2: Optional[str] = "WATCH NOW"
    seasons: Optional[str] = "1"
    episodes: Optional[str] = "12"
    year: Optional[str] = "2024"
    synopsis: Optional[str] = "No synopsis available."
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
    type: Optional[str] = "info"  # info, new_episode, new_anime, alert

def check(token: str):
    if token != BOT_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ── PUBLIC ────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "✅ Kenshin Anime API v4 running!"}

@app.get("/anime")
async def get_all():
    try:
        items = await db.anime.find({"visible": True}, {"_id": 0}).to_list(5000)
        return items
    except:
        return []

@app.get("/anime/category/{cat}")
async def by_cat(cat: str):
    return await db.anime.find({"category": cat, "visible": True}, {"_id": 0}).to_list(1000)

@app.get("/anime/title/{title}")
async def by_title(title: str):
    item = await db.anime.find_one({"title": {"$regex": f"^{title}$", "$options": "i"}, "visible": True}, {"_id": 0})
    return item or {}

@app.get("/settings")
async def public_settings():
    s = await db.settings.find_one({"_id": "site"}, {"_id": 0})
    return s or {}

@app.get("/stats")
async def stats():
    total  = await db.anime.count_documents({"visible": True})
    manwha = await db.anime.count_documents({"category": "manwha", "visible": True})
    movies = await db.anime.count_documents({"category": "movie", "visible": True})
    return {"total": total, "manwha": manwha, "movies": movies}

@app.get("/notification")
async def get_notification():
    n = await db.notifications.find_one({"active": True}, {"_id": 0}, sort=[("created_at", -1)])
    return n or {}

# ── COMMENTS (PUBLIC) ─────────────────────────────────────────────────────────
@app.post("/comments/add")
async def add_comment(data: CommentItem):
    if not data.comment.strip():
        return {"ok": False, "msg": "Comment empty hai!"}
    if len(data.comment) > 500:
        return {"ok": False, "msg": "Comment too long (max 500 chars)!"}
    doc = {
        "anime_title": data.anime_title,
        "username": (data.username or "Anonymous")[:30],
        "comment": data.comment[:500],
        "created_at": datetime.utcnow().isoformat(),
        "approved": True
    }
    await db.comments.insert_one(doc)
    return {"ok": True, "msg": "✅ Comment posted!"}

@app.get("/comments/{anime_title}")
async def get_comments(anime_title: str):
    items = await db.comments.find(
        {"anime_title": {"$regex": f"^{anime_title}$", "$options": "i"}, "approved": True},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return items

# ── DEMANDS (PUBLIC) ──────────────────────────────────────────────────────────
@app.post("/demands/add")
async def add_demand(data: DemandItem):
    if not data.title.strip():
        return {"ok": False, "msg": "Title daalo!"}
    ex = await db.demands.find_one({"title": {"$regex": f"^{data.title}$", "$options": "i"}})
    if ex:
        await db.demands.update_one(
            {"title": {"$regex": f"^{data.title}$", "$options": "i"}},
            {"$inc": {"votes": 1}}
        )
        return {"ok": True, "msg": f"✅ Vote added for '{data.title}'! Total votes: {ex.get('votes',1)+1}"}
    doc = {
        "title": data.title[:100],
        "category": data.category or "anime",
        "username": (data.username or "Anonymous")[:30],
        "reason": (data.reason or "")[:300],
        "votes": 1,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat()
    }
    await db.demands.insert_one(doc)
    return {"ok": True, "msg": f"✅ '{data.title}' demand submitted!"}

@app.get("/demands/top")
async def top_demands():
    items = await db.demands.find({"status": {"$ne": "rejected"}}, {"_id": 0}).sort("votes", -1).to_list(20)
    return items

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.post("/admin/add")
async def add(data: AnimeItem, token: str):
    check(token)
    try:
        ex = await db.anime.find_one({"title": {"$regex": f"^{data.title}$", "$options": "i"}})
        if ex:
            return {"ok": False, "msg": f"⚠️ '{data.title}' already exists!"}
        d = data.dict()
        if not d.get("dl_link1"): d["dl_link1"] = d["tg_link"]
        await db.anime.insert_one(d)
        return {"ok": True, "msg": f"✅ '{data.title}' added!"}
    except Exception as e:
        return {"ok": False, "msg": f"❌ DB Error: {str(e)}"}

@app.post("/admin/bulk")
async def bulk_add(items: List[AnimeItem], token: str):
    check(token)
    added, skipped, errors = 0, 0, []
    for item in items:
        try:
            ex = await db.anime.find_one({"title": {"$regex": f"^{item.title}$", "$options": "i"}})
            if ex:
                skipped += 1
                continue
            d = item.dict()
            if not d.get("dl_link1"): d["dl_link1"] = d["tg_link"]
            await db.anime.insert_one(d)
            added += 1
        except Exception as e:
            errors.append(f"{item.title}: {str(e)}")
    return {"ok": True, "added": added, "skipped": skipped, "errors": errors,
            "msg": f"✅ {added} added, {skipped} skipped, {len(errors)} errors"}

@app.patch("/admin/edit/{title}")
async def edit(title: str, upd: UpdateItem, token: str):
    check(token)
    r = await db.anime.update_one({"title": {"$regex": f"^{title}$", "$options": "i"}}, {"$set": {upd.field: upd.value}})
    return {"ok": r.modified_count > 0, "msg": "✅ Updated!" if r.modified_count > 0 else f"❌ '{title}' not found!"}

@app.delete("/admin/delete/{title}")
async def delete(title: str, token: str):
    check(token)
    r = await db.anime.delete_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
    return {"ok": r.deleted_count > 0, "msg": "🗑️ Deleted!" if r.deleted_count > 0 else "❌ Not found!"}

@app.delete("/admin/delete_all")
async def delete_all(token: str):
    check(token)
    r = await db.anime.delete_many({})
    return {"ok": True, "msg": f"🗑️ All {r.deleted_count} anime deleted!"}

@app.patch("/admin/hide/{title}")
async def hide(title: str, token: str):
    check(token)
    await db.anime.update_one({"title": {"$regex": f"^{title}$", "$options": "i"}}, {"$set": {"visible": False}})
    return {"ok": True, "msg": "👁️ Hidden!"}

@app.patch("/admin/show/{title}")
async def show(title: str, token: str):
    check(token)
    await db.anime.update_one({"title": {"$regex": f"^{title}$", "$options": "i"}}, {"$set": {"visible": True}})
    return {"ok": True, "msg": "✅ Visible!"}

@app.patch("/admin/move/{title}")
async def move(title: str, category: str, token: str):
    check(token)
    r = await db.anime.update_one({"title": {"$regex": f"^{title}$", "$options": "i"}}, {"$set": {"category": category}})
    return {"ok": r.modified_count > 0, "msg": f"✅ Moved to {category}!" if r.modified_count > 0 else "❌ Not found!"}

@app.get("/admin/list")
async def list_all(token: str):
    check(token)
    return await db.anime.find({}, {"_id": 0}).to_list(5000)

@app.patch("/admin/settings")
async def update_settings(token: str, field: str, value: str):
    check(token)
    await db.settings.update_one({"_id": "site"}, {"$set": {field: value}}, upsert=True)
    return {"ok": True, "msg": f"✅ '{field}' saved!"}

# ── ADMIN NOTIFICATIONS ───────────────────────────────────────────────────────
@app.post("/admin/notification")
async def push_notification(data: NotificationItem, token: str):
    check(token)
    await db.notifications.update_many({}, {"$set": {"active": False}})
    doc = {
        "message": data.message,
        "anime_title": data.anime_title or "",
        "active": True,
        "type": data.type or "info",
        "created_at": datetime.utcnow().isoformat()
    }
    await db.notifications.insert_one(doc)
    return {"ok": True, "msg": "📢 Notification sent to all users!"}

@app.delete("/admin/notification")
async def clear_notification(token: str):
    check(token)
    await db.notifications.update_many({}, {"$set": {"active": False}})
    return {"ok": True, "msg": "🔕 Notification cleared!"}

@app.get("/admin/notifications")
async def all_notifications(token: str):
    check(token)
    items = await db.notifications.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return items

# ── ADMIN COMMENTS ────────────────────────────────────────────────────────────
@app.get("/admin/comments")
async def all_comments(token: str):
    check(token)
    return await db.comments.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

@app.delete("/admin/comments/delete")
async def del_comment(token: str, anime_title: str, created_at: str):
    check(token)
    r = await db.comments.delete_one({"anime_title": anime_title, "created_at": created_at})
    return {"ok": r.deleted_count > 0, "msg": "🗑️ Comment deleted!" if r.deleted_count > 0 else "❌ Not found!"}

@app.delete("/admin/comments/clear_all")
async def clear_all_comments(token: str):
    check(token)
    r = await db.comments.delete_many({})
    return {"ok": True, "msg": f"🗑️ All {r.deleted_count} comments deleted!"}

# ── ADMIN DEMANDS ─────────────────────────────────────────────────────────────
@app.get("/admin/demands")
async def all_demands(token: str):
    check(token)
    return await db.demands.find({}, {"_id": 0}).sort("votes", -1).to_list(500)

@app.patch("/admin/demands/status")
async def update_demand_status(token: str, title: str, status: str):
    check(token)
    await db.demands.update_one({"title": title}, {"$set": {"status": status}})
    return {"ok": True, "msg": f"✅ '{title}' marked as {status}!"}

@app.delete("/admin/demands/delete")
async def del_demand(token: str, title: str):
    check(token)
    r = await db.demands.delete_one({"title": title})
    return {"ok": r.deleted_count > 0, "msg": "🗑️ Demand deleted!"}
