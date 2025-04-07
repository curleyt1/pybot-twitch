import asyncio
import logging
import sqlite3

import asqlite
import twitchio
from twitchio.ext import commands
from twitchio import eventsub

import config # Contains IDs and client secret


LOGGER: logging.Logger = logging.getLogger("Bot")

CLIENT_ID: str = config.CLIENT_ID # The CLIENT ID from the Twitch Dev Console
CLIENT_SECRET: str = config.CLIENT_SECRET # The CLIENT SECRET from the Twitch Dev Console
BOT_ID = config.BOT_ID # The Account ID of the bot user...
OWNER_ID = config.OWNER_ID # Your personal User ID..


class Bot(commands.Bot):
    def __init__(self, *, token_database: asqlite.Pool, responses_database: asqlite.Pool) -> None:
        self.token_database = token_database
        self.responses_database = responses_database
        super().__init__(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            bot_id=BOT_ID,
            owner_id=OWNER_ID,
            prefix="!",
        )

    async def setup_hook(self) -> None:
        # Add our component which contains our commands...
        await self.add_component(MyComponent(self))

        # Subscribe to read chat (event_message) from our channel as the bot...
        # This creates and opens a websocket to Twitch EventSub...
        subscription = eventsub.ChatMessageSubscription(broadcaster_user_id=OWNER_ID, user_id=BOT_ID)
        await self.subscribe_websocket(payload=subscription)

        # Subscribe and listen to when a stream goes live..
        # For this example listen to our own stream...
        subscription = eventsub.StreamOnlineSubscription(broadcaster_user_id=OWNER_ID)
        await self.subscribe_websocket(payload=subscription)

    async def add_token(self, token: str, refresh: str) -> twitchio.authentication.ValidateTokenPayload:
        # Make sure to call super() as it will add the tokens interally and return us some data...
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        # Store our tokens in a simple SQLite Database when they are authorized...
        query = """
        INSERT INTO tokens (user_id, token, refresh)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            token = excluded.token,
            refresh = excluded.refresh;
        """

        async with self.token_database.acquire() as connection:
            await connection.execute(query, (resp.user_id, token, refresh))

        LOGGER.info("Added token to the database for user: %s", resp.user_id)
        return resp

    async def load_tokens(self, path: str | None = None) -> None:
        # We don't need to call this manually, it is called in .login() from .start() internally...

        async with self.token_database.acquire() as connection:
            rows: list[sqlite3.Row] = await connection.fetchall("""SELECT * from tokens""")

        for row in rows:
            await self.add_token(row["token"], row["refresh"])

    async def setup_database(self) -> None:
        # Create our token table, if it doesn't exist..
        query = """CREATE TABLE IF NOT EXISTS tokens(user_id TEXT PRIMARY KEY, token TEXT NOT NULL, refresh TEXT NOT NULL)"""
        async with self.token_database.acquire() as connection:
            await connection.execute(query)

    async def add_response(self, command: str, response: str) -> None:
        # # Make sure to call super() as it will add the tokens interally and return us some data...
        # resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        # For custom dynamic commands, store the response in sqlite database so that it persists when bot is restarted.
        query = """
        INSERT INTO responses (command, response)
        VALUES (?, ?)
        ON CONFLICT(command)
        DO UPDATE SET
            command = excluded.command;
            response = excluded.response;
        """

        async with self.responses_database.acquire() as connection:
            await connection.execute(query, (command, response))

        LOGGER.info("Added new command", command, response)
        return resp

    # async def remove_response(self, command: str) -> None:
    #     # Delete command from dynamic responses table
    #     query = """
    #     DELETE FROM responses
    #     WHERE command=(command)
    #     VALUES (?);
    #     """

    async def load_responses(self, path: str | None = None) -> None:
        # We don't need to call this manually, it is called in .login() from .start() internally...

        async with self.responses_database.acquire() as connection:
            rows: list[sqlite3.Row] = await connection.fetchall("""SELECT * from responses""")

        for row in rows:
            await self.add_response(row["command"], row["response"])

    async def setup_responses_database(self) -> None:
        # Create our dynamic response table, if it doesn't exist..
        query = """CREATE TABLE IF NOT EXISTS responses(command TEXT PRIMARY KEY, response TEXT NOT NULL)"""
        async with self.responses_database.acquire() as connection:
            await connection.execute(query)

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)


class MyComponent(commands.Component):
    def __init__(self, bot: Bot):
        # Passing args is not required...
        # We pass bot here as an example...
        self.bot = bot

    # We use a listener in our Component to display the messages received.
    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        print(f"[{payload.broadcaster.name}] - {payload.chatter.name}: {payload.text}")

    @commands.command(aliases=["hello", "howdy", "hey"])
    async def hi(self, ctx: commands.Context) -> None:
        """Simple command that says hello!

        !hi, !hello, !howdy, !hey
        """
        await ctx.reply(f"Hello {ctx.chatter.mention}!")

    @commands.group(invoke_fallback=True)
    async def socials(self, ctx: commands.Context) -> None:
        """Group command for our social links.

        !socials
        """
        await ctx.send("https://bsky.app/profile/tcurls.net")

    @commands.is_elevated()
    @commands.command()
    async def addcommand(self, ctx: commands.Context, *, content: str ) -> None:
        # Split content of message after command, should be one word command followed by response
        content_array = content.split(' ', 1)
        command = content_array[0]
        response = content_array[1]
        try:
            await self.bot.add_response(command, response)
        except Exception as e:
            LOGGER.warning(e)
            await ctx.send("Failed to add command! :(")

    # @commands.is_elevated()
    # @commands.command()
    # async def rmcommand(self, ctx: commands.Context) -> None:
    #     async with self.remove_response(rows[""])
    #         await ctx.send("Command removed successfully!")
    
    # @commands.command()
    # async def whatis(self, ctx: commands.Context, *, content:str) -> None:
    #     async with self.get_response(content)
    #         await ctx.send("Command removed successfully!")

def main() -> None:
    twitchio.utils.setup_logging(level=logging.INFO)

    async def runner() -> None:
        async with asqlite.create_pool("tokens.db") as tdb, asqlite.create_pool("responses.db") as rdb, Bot(token_database=tdb, responses_database=rdb) as bot:
            await bot.setup_database()
            await bot.setup_responses_database()
            await bot.start()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        LOGGER.warning("Shutting down due to KeyboardInterrupt...")


if __name__ == "__main__":
    main()
