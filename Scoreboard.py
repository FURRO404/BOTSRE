import datetime
import discord
from replit.object_storage import Client
import json
import logging
import requests

client = Client()

# Set up logging
logging.basicConfig(level=logging.DEBUG)

LOG_HEADER = "--------------------------\n                 B F H T A\n"
SESSION_TEMPLATE = {
    "started": False,
    "user": None,
    "region": None,
    "wins": 0,
    "losses": 0,
    "log_entries": [],
    "last_message_id": None,
    "log": ""
}

DEFAULT_PERMISSIONS = {
    # Define your default permissions here
}

class Scoreboard:
    sessions = {}
    permissions = {}

    @classmethod
    def get_session_key(cls, guild_id):
        return f"{guild_id}_session.json"

    @classmethod
    def get_permissions_key(cls, guild_id):
        return f"{guild_id}_permissions.json"

    @classmethod
    def load_session(cls, guild_id):
        key = cls.get_session_key(guild_id)
        try:
            logging.debug(f"Attempting to download session data for guild {guild_id}")
            data = client.download_as_text(key)
            cls.sessions[guild_id] = json.loads(data)
            logging.debug(f"Loaded session data for guild {guild_id}: {cls.sessions[guild_id]}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logging.debug(f"Session data for guild {guild_id} not found, initializing new session")
                cls.sessions[guild_id] = SESSION_TEMPLATE.copy()
            else:
                logging.error(f"Error loading session data for guild {guild_id}: {e}")
                raise
        except Exception as e:
            logging.error(f"Error loading session data for guild {guild_id}: {e}")
            cls.sessions[guild_id] = SESSION_TEMPLATE.copy()

    @classmethod
    def save_session(cls, guild_id):
        key = cls.get_session_key(guild_id)
        data = json.dumps(cls.sessions[guild_id])
        logging.debug(f"Saving session data for guild {guild_id}: {data}")
        try:
            client.upload_from_text(key, data)
        except Exception as e:
            logging.error(f"Error saving session data for guild {guild_id}: {e}")

    @classmethod
    def load_permissions(cls, guild_id):
        key = cls.get_permissions_key(guild_id)
        try:
            logging.debug(f"Attempting to download permissions data for guild {guild_id}")
            data = client.download_as_text(key)
            cls.permissions[guild_id] = json.loads(data)
            logging.debug(f"Loaded permissions data for guild {guild_id}: {cls.permissions[guild_id]}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logging.debug(f"Permissions data for guild {guild_id} not found, using default permissions")
                cls.permissions[guild_id] = DEFAULT_PERMISSIONS.copy()
            else:
                logging.error(f"Error loading permissions data for guild {guild_id}: {e}")
                cls.permissions[guild_id] = DEFAULT_PERMISSIONS.copy()
        except Exception as e:
            logging.error(f"Error loading permissions data for guild {guild_id}: {e}")
            cls.permissions[guild_id] = DEFAULT_PERMISSIONS.copy()

    @classmethod
    def save_permissions(cls, guild_id):
        key = cls.get_permissions_key(guild_id)
        data = json.dumps(cls.permissions[guild_id])
        logging.debug(f"Saving permissions data for guild {guild_id}: {data}")
        try:
            client.upload_from_text(key, data)
        except Exception as e:
            logging.error(f"Error saving permissions data for guild {guild_id}: {e}")

    @classmethod
    async def start_session(cls, interaction: discord.Interaction, region: str):
        guild_id = interaction.guild.id
        cls.load_session(guild_id)
        cls.load_permissions(guild_id)

        if cls.sessions[guild_id]["started"]:
            await interaction.response.send_message("A session is already active.", ephemeral=True)
            return

        cls.sessions[guild_id] = {
            "started": True,
            "user": interaction.user.id,
            "region": region,
            "wins": 0,
            "losses": 0,
            "log_entries": [],
            "last_message_id": None,
            "log": f"{datetime.datetime.utcnow().strftime('%m/%d')}\n{LOG_HEADER}"
        }
        session_start_message = f"**{region} SESSION START - <@{cls.sessions[guild_id]['user']}>**"
        message = await interaction.channel.send(f"{session_start_message}\n```diff\n{cls.sessions[guild_id]['log']}\n```")
        cls.sessions[guild_id]["last_message_id"] = message.id

        cls.save_session(guild_id)
        cls.save_permissions(guild_id)

    @classmethod
    def format_log_entry(cls, status, wins, losses, game_number, team_name, bombers, fighters, helis, tanks, spaa, comment=''):
        spacing = "   " if len(str(wins)) == 1 and len(str(losses)) == 1 else "  " if len(str(wins)) > 1 and len(str(losses)) == 1 else "  " if len(str(wins)) == 1 and len(str(losses)) > 1 else " "
        return f"{status}{wins}-{losses}{spacing}#{game_number:<2} {team_name:<5} {bombers} {fighters} {helis} {tanks} {spaa} {comment}\n"

    @classmethod
    async def log_win(cls, interaction: discord.Interaction, team_name: str, bombers: int, fighters: int, helis: int, tanks: int, spaa: int, comment: str = ""):
        guild_id = interaction.guild.id
        cls.load_session(guild_id)

        if not cls.sessions[guild_id]["started"] or interaction.user.id != cls.sessions[guild_id]["user"]:
            await interaction.response.send_message("You are not authorized to log this win or no session is active.", ephemeral=True)
            return

        session = cls.sessions[guild_id]
        session["wins"] += 1
        game_number = session["wins"] + session["losses"]
        log_entry = cls.format_log_entry("+", session["wins"], session["losses"], game_number, team_name, bombers, fighters, helis, tanks, spaa, comment)
        session["log_entries"].append(log_entry)
        session["log"] = f"{datetime.datetime.utcnow().strftime('%m/%d')}\n{LOG_HEADER}" + "".join(session["log_entries"])

        session_start_message = f"**{session['region']} SESSION START - <@{session['user']}>**"
        if session["last_message_id"]:
            last_message = await interaction.channel.fetch_message(session["last_message_id"])
            await last_message.delete()
        message = await interaction.channel.send(f"{session_start_message}\n```diff\n{session['log']}\n```")
        session["last_message_id"] = message.id

        cls.save_session(guild_id)

    @classmethod
    async def log_loss(cls, interaction: discord.Interaction, team_name: str, bombers: int, fighters: int, helis: int, tanks: int, spaa: int, comment: str = ""):
        guild_id = interaction.guild.id
        cls.load_session(guild_id)

        if not cls.sessions[guild_id]["started"] or interaction.user.id != cls.sessions[guild_id]["user"]:
            await interaction.response.send_message("You are not authorized to log this loss or no session is active.", ephemeral=True)
            return

        session = cls.sessions[guild_id]
        session["losses"] += 1
        game_number = session["wins"] + session["losses"]
        log_entry = cls.format_log_entry("-", session["wins"], session["losses"], game_number, team_name, bombers, fighters, helis, tanks, spaa, comment)
        session["log_entries"].append(log_entry)
        session["log"] = f"{datetime.datetime.utcnow().strftime('%m/%d')}\n{LOG_HEADER}" + "".join(session["log_entries"])

        session_start_message = f"**{session['region']} SESSION START - <@{session['user']}>**"
        if session["last_message_id"]:
            last_message = await interaction.channel.fetch_message(session["last_message_id"])
            await last_message.delete()
        message = await interaction.channel.send(f"{session_start_message}\n```diff\n{session['log']}\n```")
        session["last_message_id"] = message.id

        cls.save_session(guild_id)

    @classmethod
    async def end_session(cls, interaction: discord.Interaction, bot: discord.Client):
        guild_id = interaction.guild.id
        cls.load_session(guild_id)

        if not cls.sessions[guild_id]["started"] or (interaction.user.id != cls.sessions[guild_id]["user"] and interaction.user != bot.user):
            await interaction.response.send_message("You are not authorized to end this session or no session is active.", ephemeral=True)
            return

        session = cls.sessions[guild_id]
        total_games = session["wins"] + session["losses"]
        win_rate = (session["wins"] / total_games) * 100 if total_games > 0 else 0

        session["log"] += f"\n--------------------------\nCALLED - WR: {win_rate:.2f}%\n"
        session_start_message = f"**{session['region']} SESSION START - <@{session['user']}>**"
        if session["last_message_id"]:
            last_message = await interaction.channel.fetch_message(session["last_message_id"])
            await last_message.delete()
        await interaction.channel.send(f"{session_start_message}\n```diff\n{session['log']}\n```")

        cls.sessions[guild_id] = SESSION_TEMPLATE.copy()

        cls.save_session(guild_id)

    @classmethod
    async def edit_game(cls, interaction: discord.Interaction, status: str, team_name: str, bombers: int, fighters: int, helis: int, tanks: int, spaa: int, comment: str = ""):
        guild_id = interaction.guild.id
        cls.load_session(guild_id)

        if guild_id not in cls.sessions or not cls.sessions[guild_id]["started"] or interaction.user.id != cls.sessions[guild_id]["user"]:
            await interaction.response.send_message("You are not authorized to edit a game or no session is active.", ephemeral=True)
            return

        session = cls.sessions[guild_id]
        if not session["log_entries"]:
            await interaction.response.send_message("No games have been logged yet.", ephemeral=True)
            return

        last_game_index = len(session["log_entries"]) - 1
        last_game_entry = session["log_entries"][last_game_index]
        old_status = last_game_entry.split()[0][0]

        if status == 'W' and old_status == '-':
            session["wins"] += 1
            session["losses"] -= 1
        elif status == 'L' and old_status == '+':
            session["wins"] -= 1
            session["losses"] += 1

        new_game_number = session["wins"] + session["losses"]
        new_log_entry = cls.format_log_entry("+" if status.upper() == 'W' else "-", session["wins"], session["losses"], new_game_number, team_name, bombers, fighters, helis, tanks, spaa, comment)
        session["log_entries"][last_game_index] = new_log_entry
        session["log"] = f"{datetime.datetime.utcnow().strftime('%m/%d')}\n{LOG_HEADER}" + "".join(session["log_entries"])

        session_start_message = f"**{session['region']} SESSION START - <@{session['user']}>**"
        if session["last_message_id"]:
            last_message = await interaction.channel.fetch_message(session["last_message_id"])
            await last_message.delete()
        message = await interaction.channel.send(f"{session_start_message}\n```diff\n{session['log']}\n```")
        session["last_message_id"] = message.id

        cls.save_session(guild_id)
