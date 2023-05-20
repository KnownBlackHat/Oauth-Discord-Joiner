from typing import Any, Dict, Literal, Optional, Tuple

import aiohttp
from motor.motor_asyncio import AsyncIOMotorClient

from .exceptions import (AccessTokenExpired, InvalidGrant, InvalidScope, RateLimited,
                         Unauthorized, UnkownUser)


class Oauth:
    BASE_API = "https://discord.com/api/v10"
    GRANT_TYPE = "authorization_code"

    def __init__(
        self,
        bot_token: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        session: aiohttp.ClientSession,
        mongo_uri: str,
        guild_id: str,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.session = session
        self.__bot_token = bot_token
        client = AsyncIOMotorClient(mongo_uri)
        self.db = client.get_database("oauth")
        self.guild_id = guild_id
        """
        :param bot_token: The bot token to use
        :param client_id: The client id to use
        :param client_secret: The client secret to use
        :param redirect_uri: The redirect uri to use
        :param session: The aiohttp session to use
        :param mongo_uri: The mongo uri to use
        :param guild_id: The guild id to use
        """

    async def __request(
        self,
        route: str,
        data: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
        is_bot: bool = False,
        method: Literal["GET", "POST", "PUT"] = "GET",
        json: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], int]:
        """
        Makes a request to the Discord API

        :param route: The route to make the request to
        :param data: The data to send
        :param access_token: The access token to use
        :param is_bot: Whether the token is a bot token or not
        :param method: The HTTP method to use
        :param json: The json to send
        :return: The response from the Discord API
        """
        header: Dict = {}
        if is_bot:
            header = {"Authorization": f"Bot {self.__bot_token}"}
        if access_token:
            header = {"Authorization": f"Bearer {access_token}"}

        if method == "GET":
            async with self.session.get(
                f"{self.BASE_API}{route}", headers=header
            ) as resp:
                response = await resp.json()
        elif method == "POST":
            async with self.session.post(
                f"{self.BASE_API}{route}", headers=header, data=data
            ) as resp:
                response = await resp.json()
        elif method == "PUT":
            async with self.session.put(
                f"{self.BASE_API}{route}", headers=header, json=json
            ) as resp:
                response: Dict = {}
        else:
            raise Exception(
                "Other HTTP than GET, POST and PUT are currently not Supported"
            )

        if resp.status == 401:
            raise Unauthorized(response)
        elif resp.status == 429:
            raise RateLimited(response)
        elif resp.status == 400:
            if response["error"] == "invalid_grant":
                raise InvalidGrant("Token seems expired", response)
            else:
                raise Exception("400 status code", response)
        else:
            return response, resp.status

    async def get_user(self, access_token: str) -> Tuple[str, str]:
        """
        Gets the user from the Discord API

        :param access_token: The access token to use
        :return: The user id and username
        """
        response, _ = await self.__request(
            route="/users/@me", method="GET", access_token=access_token
        )
        return (response["id"], response["username"])

    async def update_db(
        self, user: Tuple[str, str], access_token: str, refresh_token: str
    ) -> None:
        """
        Updates the database with the new access and refresh token

        :param user: The user id and username
        :param access_token: The access token to use
        :param refresh_token: The refresh token to use
        """
        await self.db.get_collection("users").update_one(
            {"_id": user[0]},
            {
                "$set": {
                    "username": user[1],
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                }
            },
            upsert=True,
        )

    async def set_access_token(self, code: str) -> Tuple[str, str, str]:
        """
        Sets the access token for the user

        :param code: The code to use
        :return: The user id, username and access token
        """
        response, _ = await self.__request(
            route="/oauth2/token",
            method="POST",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": self.GRANT_TYPE,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
        )
        if not set({"identify", "guilds.join"}).issubset(response["scope"].split(" ")):
            raise InvalidScope
        userid, username = await self.get_user(access_token=response["access_token"])
        if userid and username:
            await self.update_db(
                user=(userid, username),
                access_token=response["access_token"],
                refresh_token=response["refresh_token"],
            )
        return (userid, username, response["access_token"])

    async def set_refresh_token(self, user_id: str) -> Optional[Tuple[str, str, str]]:
        """
        Sets the access token for the user

        :param user_id: The user id to use
        :return: The user id, username and access token
        """
        db_data = await self.db.get_collection("users").find_one({"_id": user_id})
        if not db_data:
            raise UnkownUser(user_id)
        try:
            response, _ = await self.__request(
                route="/oauth2/token",
                method="POST",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": db_data["refresh_token"],
                },
            )
        except InvalidGrant:
            await self.db.get_collection("users").delete_one({"_id": user_id})
            return

        await self.update_db(
            user=(db_data["_id"], db_data["username"]),
            access_token=response["access_token"],
            refresh_token=response["refresh_token"],
        )
        return (db_data["_id"], db_data["username"], response["access_token"])

    def get_authorization_url(self) -> str:
        """
        Gets the authorization url

        :return: The authorization url
        """
        return (
            "https://discord.com/api/oauth2/authorize?"
            f"client_id={self.client_id}&redirect_uri={self.redirect_uri}"
            f"&response_type=code&scope=identify+guilds.join"
        )

    async def join(self, user_id: str) -> Literal["Success", "Already in guild"]:
        """
        Joins the user to the guild

        :param user_id: The user id to use
        :return: The response from the Discord API
        """
        db_data = await self.db.get_collection("users").find_one({"_id": user_id})
        if not db_data:
            raise UnkownUser(user_id)
        response, status = await self.__request(
            route=f"/guilds/{self.guild_id}/members/{user_id}",
            method="PUT",
            is_bot=True,
            json={"access_token": db_data["access_token"]},
        )
        if status == 201:
            return "Success"
        elif status == 204:
            return "Already in guild"
        elif status == 403:
            raise AccessTokenExpired(status, response)
        elif status == 404:
            raise UnkownUser(status, response)
        else:
            raise Exception(status, response)

    async def validate_user(self, role_id: str, code: str) -> bool:
        """
        Validates the user

        :param role_id: The role id to use
        :param code: The code to use
        :return: Whether the user is valid or not
        """
        userid, _, _ = await self.set_access_token(code=code)
        _, status = await self.__request(
            route=f"/guilds/{self.guild_id}/members/{userid}", method="GET", is_bot=True
        )
        if status == 200:
            await self.__request(
                route=f"/guilds/{self.guild_id}/members/{userid}/roles/{role_id}",
                method="PUT",
                is_bot=True,
            )
            return True
        if status == 404:
            raise UnkownUser
        return False
