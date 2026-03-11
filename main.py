"""
KENSHIN ANIME — Full Backend API
Deploy on Railway
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional
import os

app = FastAPI(title="Kenshin Anime API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URL  = os.getenv("MONGO_URL", "")
BOT_SECRET = os.getenv("BOT_SECRET", "kenshin_secret_123")

client = AsyncIOMotorClient(MONGO_URL)
db = client["kenshin_anime_db"]

# ── DATA MODEL ──────────────────────────────────────────────────────────────
class AnimeItem(BaseModel):
    title:    str
    genre:    str
    tag:      Optional[str] = ""       # HOT / NEW / MUST / TOP / CLASSIC / ONGOING
    image_url: str
    tg_link:  str
    seasons:  Optional[str] = "1"
    episodes: Optional[str] = "12"
    year:     Optional[str] = "2024"
    synopsis: Optional[str] = "No synopsis available."
    category: Optional[str] = "anime" # anime/featured/classic/new/manwha/movie
    visible:  Optional[bool] = True

class UpdateItem(BaseModel):
    field: str
    value: str

def check(token: str):
    if token != BOT_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ── PUBLIC ──────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "✅ Kenshin Anime API running!"}

@app.get("/anime")
async def get_all():
    items = await db.anime.find({"visible": True}, {"_id": 0}).to_list(2000)
    return items

@app.get("/anime/category/{cat}")
async def by_cat(cat: str):
    items = await db.anime.find({"category": cat, "visible": True}, {"_id": 0}).to_list(500)
    return items

@app.get("/anime/title/{title}")
async def by_title(title: str):
    item = await db.anime.find_one(
        {"title": {"$regex": f"^{title}$", "$options": "i"}, "visible": True},
        {"_id": 0}
    )
    return item or {}

@app.get("/stats")
async def stats():
    total   = await db.anime.count_documents({"visible": True})
    manwha  = await db.anime.count_documents({"category": "manwha", "visible": True})
    movies  = await db.anime.count_documents({"category": "movie",  "visible": True})
    return {"total": total, "manwha": manwha, "movies": movies}

# ── ADMIN ────────────────────────────────────────────────────────────────────
@app.post("/admin/add")
async def add(data: AnimeItem, token: str):
    check(token)
    ex = await db.anime.find_one({"title": {"$regex": f"^{data.title}$", "$options": "i"}})
    if ex:
        return {"ok": False, "msg": f"'{data.title}' already exists!"}
    await db.anime.insert_one(data.dict())
    return {"ok": True, "msg": f"✅ '{data.title}' added!"}

@app.patch("/admin/edit/{title}")
async def edit(title: str, upd: UpdateItem, token: str):
    check(token)
    r = await db.anime.update_one(
        {"title": {"$regex": f"^{title}$", "$options": "i"}},
        {"$set": {upd.field: upd.value}}
    )
    if r.modified_count == 0:
        return {"ok": False, "msg": f"'{title}' not found!"}
    return {"ok": True, "msg": f"✅ '{title}' → {upd.field} updated!"}

@app.delete("/admin/delete/{title}")
async def delete(title: str, token: str):
    check(token)
    r = await db.anime.delete_one({"title": {"$regex": f"^{title}$", "$options": "i"}})
    if r.deleted_count == 0:
        return {"ok": False, "msg": f"'{title}' not found!"}
    return {"ok": True, "msg": f"🗑️ '{title}' deleted!"}

@app.patch("/admin/hide/{title}")
async def hide(title: str, token: str):
    check(token)
    await db.anime.update_one(
        {"title": {"$regex": f"^{title}$", "$options": "i"}},
        {"$set": {"visible": False}}
    )
    return {"ok": True, "msg": f"👁️ '{title}' hidden!"}

@app.patch("/admin/show/{title}")
async def show(title: str, token: str):
    check(token)
    await db.anime.update_one(
        {"title": {"$regex": f"^{title}$", "$options": "i"}},
        {"$set": {"visible": True}}
    )
    return {"ok": True, "msg": f"✅ '{title}' visible again!"}

@app.get("/admin/list")
async def list_all(token: str):
    check(token)
    items = await db.anime.find({}, {"_id": 0}).to_list(2000)
    return items

@app.patch("/admin/move/{title}")
async def move_category(title: str, category: str, token: str):
    """Anime ko kisi bhi category mein move karo"""
    check(token)
    r = await db.anime.update_one(
        {"title": {"$regex": f"^{title}$", "$options": "i"}},
        {"$set": {"category": category}}
    )
    if r.modified_count == 0:
        return {"ok": False, "msg": f"'{title}' not found!"}
    return {"ok": True, "msg": f"✅ '{title}' moved to '{category}'!"}
