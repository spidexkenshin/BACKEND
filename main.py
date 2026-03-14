from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
import os
import re

app = FastAPI(title="Kenshin Anime API v6")
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

# ── MODELS ──────────────────────────────────────────────

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

class SubtitleTrack(BaseModel):
    label: str
    url: str

class EpisodeItem(BaseModel):
    anime_title: str
    season: Optional[int] = 1
    number: int
    title: Optional[str] = ""
    url: str
    thumbnail: Optional[str] = ""
    duration: Optional[str] = ""
    isNew: Optional[bool] = False
    subtitles: Optional[List[SubtitleTrack]] = []

class BulkEpisodes(BaseModel):
    anime_title: str
    seasons: Optional[List[dict]] = []
    episodes: List[dict]

# ── PUBLIC ───────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "Kenshin Anime API v6 running!"}

@app.get("/anime")
async def get_all():
    try:
        return await db.anime.find({"visible": True}, {"_id": 0}).to_list(5000)
    except:
        return []

@app.get("/anime/title/{title}")
async def get_by_title(title: str):
    doc = await db.anime.find_one(
        {"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}, "visible": True}, {"_id": 0})
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

@app.get("/stats")
async def stats():
    total    = await db.anime.count_documents({"visible": True})
    manwha   = await db.anime.count_documents({"category": "manwha", "visible": True})
    movies   = await db.anime.count_documents({"category": "movie", "visible": True})
    ep_count = await db.episodes.count_documents({})
    return {"total": total, "manwha": manwha, "movies": movies, "episodes": ep_count}

# ── EPISODES (PUBLIC) ────────────────────────────────────

@app.get("/episodes/{anime_title}")
async def get_episodes(anime_title: str):
    eps = await db.episodes.find(
        {"anime_title": {"$regex": f"^{re.escape(anime_title)}$", "$options": "i"}},
        {"_id": 0}
    ).sort([("season", 1), ("number", 1)]).to_list(10000)

    seasons_raw = await db.seasons.find(
        {"anime_title": {"$regex": f"^{re.escape(anime_title)}$", "$options": "i"}},
        {"_id": 0}
    ).sort("season", 1).to_list(100)

    if not seasons_raw and eps:
        nums = sorted(set(e.get("season", 1) for e in eps))
        seasons_raw = [{"season": s, "label": f"Season {s}"} for s in nums]

    for i, ep in enumerate(eps):
        ep["id"] = f"s{ep.get('season',1)}e{ep.get('number', i+1)}"

    return {"episodes": eps, "seasons": seasons_raw}

# ── COMMENTS ────────────────────────────────────────────

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

# ── DEMANDS ──────────────────────────────────────────────

@app.post("/demands/add")
async def add_demand(data: DemandItem):
    doc = data.dict()
    doc["created_at"] = datetime.utcnow().isoformat()
    doc["status"] = "pending"
    doc["votes"] = 1
    ex = await db.demands.find_one({"title": {"$regex": f"^{re.escape(data.title)}$", "$options": "i"}})
    if ex:
        await db.demands.update_one({"_id": ex["_id"]}, {"$inc": {"votes": 1}})
        return {"ok": True, "msg": f"Vote added for '{data.title}'!"}
    await db.demands.insert_one(doc)
    return {"ok": True, "msg": f"Demand submitted for '{data.title}'!"}

@app.get("/demands/top")
async def top_demands():
    return await db.demands.find(
        {"status": {"$ne": "rejected"}},
        {"_id": 0, "title": 1, "category": 1, "username": 1, "reason": 1, "votes": 1, "status": 1}
    ).sort("votes", -1).to_list(20)

# ── ADMIN: ANIME ─────────────────────────────────────────

@app.post("/admin/add")
async def admin_add(data: AnimeItem, token: str):
    auth(token)
    ex = await db.anime.find_one({"title": {"$regex": f"^{re.escape(data.title)}$", "$options": "i"}})
    if ex:
        return {"ok": False, "msg": f"'{data.title}' already exists!"}
    d = data.dict()
    if not d.get("dl_link1"):
        d["dl_link1"] = d["tg_link"]
    await db.anime.insert_one(d)
    return {"ok": True, "msg": f"'{data.title}' added!"}

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
            "msg": f"{added} added, {skipped} skipped"}

@app.patch("/admin/edit/{title}")
async def admin_edit(title: str, upd: UpdateItem, token: str):
    auth(token)
    r = await db.anime.update_one(
        {"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}},
        {"$set": {upd.field: upd.value}})
    return {"ok": r.modified_count > 0, "msg": "Updated!" if r.modified_count > 0 else "Not found"}

@app.delete("/admin/delete/{title}")
async def admin_delete(title: str, token: str):
    auth(token)
    r = await db.anime.delete_one({"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}})
    await db.episodes.delete_many({"anime_title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}})
    await db.seasons.delete_many({"anime_title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}})
    return {"ok": r.deleted_count > 0, "msg": "Deleted!" if r.deleted_count > 0 else "Not found"}

@app.delete("/admin/delete-all")
async def admin_delete_all(token: str):
    auth(token)
    r = await db.anime.delete_many({})
    await db.episodes.delete_many({})
    await db.seasons.delete_many({})
    return {"ok": True, "msg": f"All {r.deleted_count} anime deleted!", "count": r.deleted_count}

@app.delete("/admin/delete-category/{cat}")
async def admin_delete_cat(cat: str, token: str):
    auth(token)
    r = await db.anime.delete_many({"category": cat})
    return {"ok": True, "msg": f"{r.deleted_count} '{cat}' deleted!"}

@app.patch("/admin/hide/{title}")
async def admin_hide(title: str, token: str):
    auth(token)
    await db.anime.update_one({"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}}, {"$set": {"visible": False}})
    return {"ok": True, "msg": "Hidden!"}

@app.patch("/admin/show/{title}")
async def admin_show(title: str, token: str):
    auth(token)
    await db.anime.update_one({"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}}, {"$set": {"visible": True}})
    return {"ok": True, "msg": "Visible!"}

@app.patch("/admin/move/{title}")
async def admin_move(title: str, category: str, token: str):
    auth(token)
    r = await db.anime.update_one(
        {"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}},
        {"$set": {"category": category}})
    return {"ok": r.modified_count > 0, "msg": f"Moved to {category}!" if r.modified_count > 0 else "Not found"}

@app.get("/admin/list")
async def admin_list(token: str):
    auth(token)
    return await db.anime.find({}, {"_id": 0}).to_list(5000)

# ── ADMIN: EPISODES ──────────────────────────────────────

@app.post("/admin/episodes/add")
async def admin_add_episode(data: EpisodeItem, token: str):
    auth(token)
    doc = data.dict()
    doc["created_at"] = datetime.utcnow().isoformat()
    ex = await db.episodes.find_one({
        "anime_title": {"$regex": f"^{re.escape(data.anime_title)}$", "$options": "i"},
        "season": data.season, "number": data.number
    })
    if ex:
        await db.episodes.update_one({"_id": ex["_id"]}, {"$set": doc})
        return {"ok": True, "msg": f"S{data.season}E{data.number} updated!"}
    await db.episodes.insert_one(doc)
    count = await db.episodes.count_documents(
        {"anime_title": {"$regex": f"^{re.escape(data.anime_title)}$", "$options": "i"}})
    await db.anime.update_one(
        {"title": {"$regex": f"^{re.escape(data.anime_title)}$", "$options": "i"}},
        {"$set": {"episodes": str(count)}})
    return {"ok": True, "msg": f"S{data.season}E{data.number} added!"}

@app.post("/admin/episodes/bulk")
async def admin_bulk_episodes(data: BulkEpisodes, token: str):
    auth(token)
    added = updated = 0
    for ep in data.episodes:
        ep["anime_title"] = data.anime_title
        ep["created_at"] = datetime.utcnow().isoformat()
        ex = await db.episodes.find_one({
            "anime_title": {"$regex": f"^{re.escape(data.anime_title)}$", "$options": "i"},
            "season": ep.get("season", 1), "number": ep.get("number", 0)
        })
        if ex:
            await db.episodes.update_one({"_id": ex["_id"]}, {"$set": ep})
            updated += 1
        else:
            await db.episodes.insert_one(dict(ep))
            added += 1
    for s in data.seasons:
        s["anime_title"] = data.anime_title
        ex = await db.seasons.find_one({
            "anime_title": {"$regex": f"^{re.escape(data.anime_title)}$", "$options": "i"},
            "season": s.get("season", 1)
        })
        if ex:
            await db.seasons.update_one({"_id": ex["_id"]}, {"$set": s})
        else:
            await db.seasons.insert_one(dict(s))
    total_eps = await db.episodes.count_documents(
        {"anime_title": {"$regex": f"^{re.escape(data.anime_title)}$", "$options": "i"}})
    total_s = await db.seasons.count_documents(
        {"anime_title": {"$regex": f"^{re.escape(data.anime_title)}$", "$options": "i"}})
    await db.anime.update_one(
        {"title": {"$regex": f"^{re.escape(data.anime_title)}$", "$options": "i"}},
        {"$set": {"episodes": str(total_eps), "seasons": str(max(total_s, 1))}})
    return {"ok": True, "added": added, "updated": updated, "msg": f"{added} added, {updated} updated!"}

@app.get("/admin/episodes/{anime_title}")
async def admin_get_episodes(anime_title: str, token: str):
    auth(token)
    eps = await db.episodes.find(
        {"anime_title": {"$regex": f"^{re.escape(anime_title)}$", "$options": "i"}},
        {"_id": 1, "season": 1, "number": 1, "title": 1, "url": 1, "thumbnail": 1, "duration": 1, "isNew": 1}
    ).sort([("season", 1), ("number", 1)]).to_list(10000)
    seasons = await db.seasons.find(
        {"anime_title": {"$regex": f"^{re.escape(anime_title)}$", "$options": "i"}},
        {"_id": 0}).sort("season", 1).to_list(100)
    return {"episodes": [fix_id(e) for e in eps], "seasons": seasons}

@app.delete("/admin/episodes/item/{ep_id}")
async def admin_delete_episode(ep_id: str, token: str):
    auth(token)
    ep = await db.episodes.find_one({"_id": ObjectId(ep_id)})
    await db.episodes.delete_one({"_id": ObjectId(ep_id)})
    if ep:
        count = await db.episodes.count_documents(
            {"anime_title": {"$regex": f"^{re.escape(ep.get('anime_title',''))}$", "$options": "i"}})
        await db.anime.update_one(
            {"title": {"$regex": f"^{re.escape(ep.get('anime_title',''))}$", "$options": "i"}},
            {"$set": {"episodes": str(count)}})
    return {"ok": True, "msg": "Episode deleted!"}

@app.delete("/admin/episodes/clear/{anime_title}")
async def admin_clear_episodes(anime_title: str, token: str):
    auth(token)
    r = await db.episodes.delete_many(
        {"anime_title": {"$regex": f"^{re.escape(anime_title)}$", "$options": "i"}})
    await db.seasons.delete_many(
        {"anime_title": {"$regex": f"^{re.escape(anime_title)}$", "$options": "i"}})
    await db.anime.update_one(
        {"title": {"$regex": f"^{re.escape(anime_title)}$", "$options": "i"}},
        {"$set": {"episodes": "0"}})
    return {"ok": True, "msg": f"{r.deleted_count} episodes cleared!"}

# ── ADMIN: SETTINGS ──────────────────────────────────────

@app.patch("/admin/settings")
async def admin_settings(token: str, field: str, value: str):
    auth(token)
    await db.settings.update_one({"_id": "site"}, {"$set": {field: value}}, upsert=True)
    return {"ok": True, "msg": f"'{field}' saved!"}

# ── ADMIN: NOTIFICATIONS ─────────────────────────────────

@app.post("/admin/notifications/push")
async def push_notification(data: NotificationItem, token: str):
    auth(token)
    doc = data.dict()
    doc["created_at"] = datetime.utcnow().isoformat()
    await db.notifications.insert_one(doc)
    return {"ok": True, "msg": "Notification pushed!"}

@app.get("/admin/notifications")
async def admin_notifs(token: str):
    auth(token)
    items = await db.notifications.find(
        {}, {"_id": 1, "message": 1, "anime_title": 1, "active": 1, "type": 1, "created_at": 1}).to_list(100)
    return [fix_id(i) for i in items]

@app.delete("/admin/notifications/{nid}")
async def del_notif(nid: str, token: str):
    auth(token)
    await db.notifications.delete_one({"_id": ObjectId(nid)})
    return {"ok": True, "msg": "Deleted!"}

@app.patch("/admin/notifications/{nid}/toggle")
async def toggle_notif(nid: str, token: str):
    auth(token)
    doc = await db.notifications.find_one({"_id": ObjectId(nid)})
    if not doc:
        return {"ok": False, "msg": "Not found"}
    await db.notifications.update_one({"_id": ObjectId(nid)}, {"$set": {"active": not doc.get("active", True)}})
    return {"ok": True}

# ── ADMIN: COMMENTS ──────────────────────────────────────

@app.get("/admin/comments")
async def admin_comments(token: str):
    auth(token)
    items = await db.comments.find(
        {}, {"_id": 1, "anime_title": 1, "username": 1, "comment": 1, "created_at": 1}).to_list(500)
    return [fix_id(i) for i in items]

@app.delete("/admin/comments/{cid}")
async def del_comment(cid: str, token: str):
    auth(token)
    await db.comments.delete_one({"_id": ObjectId(cid)})
    return {"ok": True, "msg": "Deleted!"}

# ── ADMIN: DEMANDS ───────────────────────────────────────

@app.get("/admin/demands")
async def admin_demands(token: str):
    auth(token)
    items = await db.demands.find(
        {}, {"_id": 1, "title": 1, "category": 1, "username": 1, "reason": 1, "votes": 1, "status": 1, "created_at": 1}
    ).to_list(500)
    return [fix_id(i) for i in items]

@app.patch("/admin/demands/{did}")
async def update_demand(did: str, status: str, token: str):
    auth(token)
    await db.demands.update_one({"_id": ObjectId(did)}, {"$set": {"status": status}})
    return {"ok": True, "msg": f"Status: {status}"}

@app.delete("/admin/demands/{did}")
async def del_demand(did: str, token: str):
    auth(token)
    await db.demands.delete_one({"_id": ObjectId(did)})
    return {"ok": True, "msg": "Deleted!"}
