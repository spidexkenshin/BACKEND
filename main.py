from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import Optional
import os

app = FastAPI()

@app.middleware("http")
async def cors_all(request: Request, call_next):
    if request.method == "OPTIONS":
        return JSONResponse({}, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,PATCH,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "*",
        })
    resp = await call_next(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

MONGO_URL  = os.getenv("MONGO_URL","")
BOT_SECRET = os.getenv("BOT_SECRET","kenshin_secret_123")
client = AsyncIOMotorClient(MONGO_URL)
db = client["kenshin_db"]

class AnimeItem(BaseModel):
    title:str; genre:str; tag:Optional[str]=""; image_url:str; tg_link:str
    seasons:Optional[str]="1"; episodes:Optional[str]="12"; year:Optional[str]="2024"
    synopsis:Optional[str]="No synopsis."; category:Optional[str]="anime"; visible:Optional[bool]=True

class UpdItem(BaseModel):
    field:str; value:str

def ok_token(t): return t == BOT_SECRET

@app.get("/")
async def root(): return {"status":"✅ Kenshin Anime API running!"}

@app.get("/anime")
async def get_all():
    return await db.anime.find({"visible":True},{"_id":0}).to_list(2000)

@app.get("/stats")
async def stats():
    return {
        "total":  await db.anime.count_documents({"visible":True}),
        "manwha": await db.anime.count_documents({"category":"manwha","visible":True}),
        "movies": await db.anime.count_documents({"category":"movie","visible":True}),
    }

@app.post("/admin/add")
async def add(item:AnimeItem, token:str=""):
    if not ok_token(token): return {"ok":False,"msg":"❌ Wrong token!"}
    if await db.anime.find_one({"title":{"$regex":f"^{item.title}$","$options":"i"}}):
        return {"ok":False,"msg":f"⚠️ '{item.title}' already exists!"}
    await db.anime.insert_one(item.dict())
    return {"ok":True,"msg":f"✅ '{item.title}' website pe add ho gaya!"}

@app.patch("/admin/edit/{title}")
async def edit(title:str, upd:UpdItem, token:str=""):
    if not ok_token(token): return {"ok":False,"msg":"❌ Wrong token!"}
    r = await db.anime.update_one({"title":{"$regex":f"^{title}$","$options":"i"}},{"$set":{upd.field:upd.value}})
    return {"ok":r.modified_count>0,"msg":f"✅ '{title}' updated!" if r.modified_count else f"❌ '{title}' not found!"}

@app.delete("/admin/delete/{title}")
async def delete(title:str, token:str=""):
    if not ok_token(token): return {"ok":False,"msg":"❌ Wrong token!"}
    r = await db.anime.delete_one({"title":{"$regex":f"^{title}$","$options":"i"}})
    return {"ok":r.deleted_count>0,"msg":f"🗑️ '{title}' deleted!" if r.deleted_count else f"❌ Not found!"}

@app.patch("/admin/hide/{title}")
async def hide(title:str, token:str=""):
    if not ok_token(token): return {"ok":False,"msg":"❌ Wrong token!"}
    await db.anime.update_one({"title":{"$regex":f"^{title}$","$options":"i"}},{"$set":{"visible":False}})
    return {"ok":True,"msg":f"👁️ '{title}' hidden from website!"}

@app.patch("/admin/show/{title}")
async def show(title:str, token:str=""):
    if not ok_token(token): return {"ok":False,"msg":"❌ Wrong token!"}
    await db.anime.update_one({"title":{"$regex":f"^{title}$","$options":"i"}},{"$set":{"visible":True}})
    return {"ok":True,"msg":f"✅ '{title}' visible again!"}

@app.patch("/admin/move/{title}")
async def move(title:str, category:str, token:str=""):
    if not ok_token(token): return {"ok":False,"msg":"❌ Wrong token!"}
    r = await db.anime.update_one({"title":{"$regex":f"^{title}$","$options":"i"}},{"$set":{"category":category}})
    return {"ok":r.modified_count>0,"msg":f"✅ '{title}' moved to '{category}'!" if r.modified_count else "❌ Not found!"}

@app.get("/admin/list")
async def list_all(token:str=""):
    if not ok_token(token): return []
    return await db.anime.find({},{"_id":0}).to_list(2000)
