import os
from typing import Optional

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from discord_oauth.oauth import Oauth, UnkownUser

app = FastAPI()
app.auth: Oauth  # type: ignore
load_dotenv()


@app.on_event("startup")
async def start():
    app.auth = Oauth(  # type: ignore
        bot_token=os.getenv("bot_token"),
        client_id=os.getenv("client_id"),
        client_secret=os.getenv("client_secret"),
        redirect_uri=os.getenv("redirect_uri"),
        session=aiohttp.ClientSession(),
        mongo_uri=os.getenv("mongo_uri"),
        guild_id=os.getenv("guild_id"),
    )


@app.get("/")
async def root():
    return RedirectResponse(url="https://discord.com/app", status_code=302)


@app.get("/join_all")
async def joinall():
    await app.auth.join_all()  # type: ignore
    return "Done"


@app.get("/refresh_all")
async def refresh():
    await app.auth.join_all()  # type: ignore
    await app.auth.refresh_all()  # type: ignore
    return "Done"


@app.get("/callback")
async def callback(code: Optional[str] = None):
    if code:
        try:
            await app.auth.validate_user(code=code, role_id="1108496066111885322")  # type: ignore
        except UnkownUser:
            ...

    return RedirectResponse(
        url=f"https://discord.com/app", status_code=302  # type: ignore
    )


@app.get("/auth")
async def auth():
    return RedirectResponse(app.auth.get_authorization_url())  # type: ignore


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)  # type: ignore
