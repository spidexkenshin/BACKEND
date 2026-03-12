from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional, List
import os

app = FastAPI(title="Kenshin Anime API v3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

MONGO_URL  = os.getenv("MONGO_URL", "")
BOT_SECRET = os.getenv("BOT_SECRET", "kenshin_secret_123")
client = AsyncIOMotorClient(MONGO_URL)
db = client["kenshin_anime_db"]

class AnimeItem(BaseModel):
    title:    str
    genre:    str
    tag:      Optional[str] = ""
    image_url: str
    tg_link:  str
    dl_link1: Optional[str] = ""   # Download button 1
    dl_link2: Optional[str] = ""   # Download button 2
    dl_label1: Optional[str] = "Watch Free"
    dl_label2: Optional[str] = "Download HD"
    seasons:  Optional[str] = "1"
    episodes: Optional[str] = "12"
    year:     Optional[str] = "2024"
    synopsis: Optional[str] = "No synopsis available."
    category: Optional[str] = "anime"
    visible:  Optional[bool] = True

class UpdateItem(BaseModel):
    field: str
    value: str

def check(token: str):
    if token != BOT_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ── PUBLIC ────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "✅ Kenshin Anime API v3 running!"}

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
    return {"ok": r.modified_count > 0, "msg": f"✅ Updated!" if r.modified_count > 0 else f"❌ '{title}' not found!"}

@app.delete("/admin/delete/{title}")
async def delete(title: str, token: str):
    check(token)
    r = await db.anime.delete_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
    return {"ok": r.deleted_count > 0, "msg": f"🗑️ Deleted!" if r.deleted_count > 0 else "❌ Not found!"}

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
