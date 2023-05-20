import asyncio
import os
from typing import Set
import logging

import aiohttp
import disnake
from disnake.ext import commands
from dotenv import load_dotenv

from discord_oauth.exceptions import (AccessTokenExpired, InvalidGrant,
                                      UnkownUser)
from discord_oauth.oauth import Oauth


log = logging.getLogger(__name__)


class VerificationBot(commands.Bot):
    def __init__(self, session, **kwargs):
        super().__init__(**kwargs)
        self.session = session


async def main():
    async with aiohttp.ClientSession() as session:
        load_dotenv()
        oauth = Oauth(
            bot_token=os.getenv("bot_token"),
            client_id=os.getenv("client_id"),
            client_secret=os.getenv("client_secret"),
            redirect_uri=os.getenv("redirect_uri"),
            session=aiohttp.ClientSession(),
            mongo_uri=os.getenv("mongo_uri"),
            guild_id=os.getenv("guild_id"),
        )
        client = VerificationBot(
            command_prefix="!!", intents=disnake.Intents.all(), session=session
        )

        @client.event
        async def on_ready():
            log.info("Verification Bot is ready")

        @client.command()
        @commands.has_permissions(manage_guild=True)
        async def verify(ctx: commands.GuildContext, url: str):
            """
            This command is used to create a verification embed

            Parameters
            ----------
            url: Url to redirect to for verification
            """
            await ctx.send(
                embed=disnake.Embed(
                    title="Verification System",
                    color=disnake.Color.blue(),
                    description="Click the button below to verify your account",
                ).set_image(url="https://cdn.discordapp.com/attachments/1109179149601476648/1109387623719510066/digital-fingerprint-scanning-verification-process.png"),
                components=[
                    disnake.ui.Button(
                        style=disnake.ButtonStyle.green, label="Verify", url=url
                    )
                ],
            )

        @client.command()
        @commands.has_permissions(manage_guild=True)
        async def join_all(ctx: commands.GuildContext):
            """
            This command is used to join all members in the database to the guild
            """
            guild_members: Set = {str(member.id) for member in ctx.guild.members}
            db_members: Set = {
                member["_id"]
                async for member in oauth.db.get_collection("users").find()
            }
            completed: Set = set()
            await ctx.send(
                    f"""
                    Guild members: {len(guild_members)}\n
                    Database members: {len(db_members)}\n
                    Members to join: {len(db_members - guild_members)}\n
                    Members: {", ".join(db_members - guild_members)}
                    """
                    )
            embed = disnake.Embed(
                title="Joining Members",
                color=disnake.Color.random(),
                description="\n".join(completed),
            )
            msg = await ctx.send(embed=embed)
            for member in db_members - guild_members:
                await asyncio.sleep(1)
                try:
                    await oauth.join(member)
                except (UnkownUser, InvalidGrant, AccessTokenExpired):
                    refresh_resp = await oauth.set_refresh_token(member)
                    if not refresh_resp:
                        continue
                    try:
                        await oauth.join(refresh_resp[-1])
                    except AccessTokenExpired:
                        await oauth.db.get_collection("users").delete_one({"_id": refresh_resp[-1]})
                        continue
                completed.add(member)
                new_embed = disnake.Embed(
                    title="Joining members...",
                    color=disnake.Color.random(),
                    description="\n".join(completed),
                )
                await msg.edit(embed=new_embed)
            await ctx.send("Completed joining members")

        @client.command()
        @commands.has_permissions(manage_guild=True)
        async def refresh_all(ctx: commands.GuildContext):
            """
            This command is used to refresh all members in the database
            """
            try:
                await join_all(ctx)
                async for member in oauth.db.get_collection("users").find():
                    await oauth.set_refresh_token(user_id=member["_id"])
            except (UnkownUser, InvalidGrant):
                ...
            await ctx.send("Completed refreshing members")

        try:
            await client.start(os.getenv("bot_token"))  # type: ignore
        except (disnake.LoginFailure, disnake.HTTPException):
            log.critical("Invalid token")
        finally:
            await client.session.close()


asyncio.run(main())
