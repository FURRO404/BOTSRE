# Standard Library Imports
import asyncio
import datetime as DT
import json
import logging
import math
import os
import re
import shutil
import time as T
import traceback

# Third-Party Library Imports
from contextlib import suppress
from datetime import datetime, time, timezone

import deepl
import discord
from discord import ButtonStyle, Color, Embed, Interaction, app_commands
from discord.ext import commands, tasks
from discord.ui import View, button
from discord.utils import escape_markdown
from replit.object_storage import Client
from replit.object_storage.errors import ObjectNotFoundError

# Local Module Imports
import Alarms
from AutoLog import fetch_games_for_user
from Data_Parser import LangTableReader, get_dict_from_list
from Leaderboard_Parser import get_top_20, search_for_clan
from Parse_Replay import get_basic_replay_info, save_replay_data
from Scoreboard import create_scoreboard
from SQ_Info import fetch_squadron_info

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("deepl").setLevel(logging.WARNING)

client = Client(bucket_id="replit-objstore-b5261a8a-c768-4543-975e-dfce1cd7077d")
TOKEN = os.environ.get('DISCORD_KEY')

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
intents.messages = True


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='~', intents=intents)
        self.synced = False

    async def setup_hook(self):
        await self.tree.sync()
        self.synced = True

bot = MyBot()


@bot.event
async def on_ready():
    logging.info(f'We have logged in as {bot.user} in the following guilds:')
    
    for guild in bot.guilds:
        logging.info(f' - {guild.name} (id: {guild.id})')
        
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.playing, name="War Thunder"))
    
    if not bot.synced:
        await bot.tree.sync()
        bot.synced = True

    try:
        await cleanup_replays()
        logging.info("Wiped replays . . .")
    except Exception as e:
        logging.error(f"Error wiping replays in startup: {e}")

    try:
        await search_for_clan("AVR")
        logging.info("Initialized cache . . .")
    except Exception as e:
        logging.error(f"Error initializing cache in startup: {e}")

    try:
        points_alarm_task.start()
        auto_logging_task.start()
        replay_cleaning_task.start()
        
        logging.info("Engines 1-3 are a go . . .")
        logging.info("We have liftoff ! ! !")
        
    except Exception as e:
        logging.error(f"Error starting tasks in startup: {e}")
    
    #region = "EU"
    #await execute_points_alarm_task(region)


@bot.event
async def on_guild_join(guild):
    logging.info(f'Joined new guild: {guild.name} (id: {guild.id})')
    await bot.tree.sync()
    guild_id = guild.id
    key = "guilds.json"

    try:
        data = client.download_as_text(key)
        guilds = json.loads(data)
    except ObjectNotFoundError:
        guilds = []

    if guild_id not in guilds:
        guilds.append(guild_id)
        client.upload_from_text(key, json.dumps(guilds))


@tasks.loop(hours=2)
async def replay_cleaning_task():
    try:
        now_utc = datetime.now(timezone.utc).time()

        US_START = time(1, 00)
        US_END = time(7, 00)
        EU_START = time(14, 00)
        EU_END = time(22, 00)

        if US_START <= now_utc <= US_END or EU_START <= now_utc <= EU_END:
            logging.info("PURGING OLD REPLAY FOLDERS")
            await purge_old_replay_folders()

    except Exception as e:
        logging.error(f"Unhandled exception in replay_cleaning: {e}")


async def purge_old_replay_folders():
    current_time = T.time()
    replay_file_path = "replays/"

    if os.path.exists(replay_file_path):
        for folder in os.listdir(replay_file_path):
            folder_path = os.path.join(replay_file_path, folder)
            folder_c_time = os.path.getmtime(folder_path)
            # If the folder's modification time is older than 1 hour, delete it
            if folder_c_time < current_time - 3600:
               await asyncio.to_thread(shutil.rmtree, folder_path)

@replay_cleaning_task.before_loop
async def before_replay_cleaning_task():
    await bot.wait_until_ready()



@tasks.loop(minutes=1)
async def points_alarm_task():
    now_utc = datetime.now(timezone.utc).time()

    if now_utc.hour == 22 and now_utc.minute == 30:
        region = "EU"
        await execute_points_alarm_task(region)
    elif now_utc.hour == 7 and now_utc.minute == 30:
        region = "US"
        await execute_points_alarm_task(region)


async def execute_points_alarm_task(region):
    await cleanup_replays()
    logging.info("Running points-update alarm")
    for guild in bot.guilds:
        guild_id = guild.id
        guild_name = guild.name
        key = f"PREFERENCES/{guild_id}-preferences.json"

        logging.info(f"(POINTS) Processing guild: {guild_id} for region: {region}")

        try:
            data = client.download_as_text(key)
            preferences = json.loads(data)
            logging.info(f"(POINTS) Successfully loaded preferences for guild: {guild_id}")
            
        except (ObjectNotFoundError, FileNotFoundError):
            preferences = {}

        for squadron_name, squadron_preferences in preferences.items():
            logging.info(f"(POINTS) Checking squadron: {squadron_name} for points alarm")

            squadron_info = await fetch_squadron_info(squadron_name, embed_type="points")
            if squadron_info.fields and squadron_info.fields[0].value:
                sq_total_points = int(squadron_info.fields[0].value.replace(",", ""))
            else:
                sq_total_points = 0  # Default value if no valid data

            logging.info(f"{squadron_name} points at {sq_total_points}.")

            if "Points" in squadron_preferences:
                opposite_region = "EU" if region == "US" else "US"
                old_snapshot = Alarms.load_snapshot(guild_id, squadron_name, opposite_region)
                new_snapshot = await Alarms.take_snapshot(squadron_name)

                if old_snapshot:
                    points_changes, old_total_points = Alarms.compare_points(old_snapshot, new_snapshot)

                    if points_changes:
                        channel_id = squadron_preferences.get("Points", "")
                        try:
                            channel_id = int(channel_id.strip("<#>"))
                        except Exception:
                            logging.error(f"(POINTS) Failed to get channel ID in {guild_name} ({guild_id}), skipping")
                            continue
                            
                        if channel_id > 0:
                            channel = bot.get_channel(channel_id)
                            if channel:
                                logging.info(f"(POINTS) Sending points update to channel {channel_id} for squadron {squadron_name}")

                                changes_lines = []

                                for member, (points_change, current_points) in points_changes.items():
                                    arrow = "🌲" if points_change > 0 else "🔻"
                                    member_str = f"{member:<20}"[:20]  # Limit name to 20 characters
                                    change_str = f"{arrow} {abs(points_change):<5}"  # Change column width of 5
                                    current_points_str = f"{current_points:>8}"  # Right-aligned 8 width
                                    changes_lines.append(f"{member_str}{change_str}{current_points_str}")

                                # Chunk the lines into sections that fit within the max_field_length limit
                                max_field_length = 1024
                                chunks = []
                                current_chunk = "```\nName                Change       Now\n"
                                for line in changes_lines:
                                    if len(current_chunk) + len(line) + 1 > max_field_length:
                                        current_chunk += "```"
                                        chunks.append(current_chunk)
                                        current_chunk = "```\n" + line + "\n"
                                    else:
                                        current_chunk += line + "\n"

                                # Add any remaining text in the last chunk
                                if current_chunk:
                                    current_chunk += "```"
                                    chunks.append(current_chunk)

                                chart = "📈" if old_total_points < int(sq_total_points) else "📉"
                                embed = discord.Embed(
                                    title=
                                    f"**{squadron_name} {region} Points Update**",
                                    description=
                                    f"# **Point Change:** {old_total_points} -> {sq_total_points} {chart}\n\n**Player Changes:**",
                                    color=discord.Color.blue())

                                for chunk in chunks:
                                    embed.add_field(name="\u200A", value=chunk, inline=False)
                                embed.set_footer(text="Meow :3")

                                
                                try:
                                    await channel.send(embed=embed)
                                    logging.info(f"(POINTS) Points update sent successfully for {squadron_name} in {guild_id}")

                                except Exception as e:
                                    logging.error(f"(POINTS) Error sending points update to {guild_name} ({guild_id}): {e}")
                                    continue

                            else:
                                logging.error(f"(POINTS) Channel ID {channel_id} not found for guild {guild_id}")
                        else:
                            logging.error(f"(POINTS) Invalid channel ID format: {channel_id} for squadron {squadron_name} in {guild_name} ({guild_id})")
                    else:
                        logging.info(f"(POINTS) No new points for {squadron_name}")

                # Save the new snapshot with the region specified
                Alarms.save_snapshot(new_snapshot, guild_id, squadron_name,
                                     region)
                logging.info(f"(POINTS) New snapshot saved for {squadron_name} in region {region}")


@points_alarm_task.before_loop
async def before_points_alarm_task():
    await bot.wait_until_ready()


def get_shortname_from_long(longname):
    squadrons_str = client.download_as_text("SQUADRONS.json")
    squadrons = json.loads(squadrons_str)

    # Iterate through the dictionary to find the matching long name
    for _, squadron_info in squadrons.items():
        if squadron_info["SQ_LongHandName"] == longname:
            return squadron_info["SQ_ShortHand_Name"]

    return None


def load_active_guilds(guild_id):
    guild_id = str(guild_id)
    try:
        with open("ACTIVE_GUILDS.json", "r", encoding="utf-8") as file:
            data = json.load(file)
        return guild_id in data.get("activated", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def load_guild_preferences(guild_id):
    key = f"PREFERENCES/{guild_id}-preferences.json"
    try:
        data = client.download_as_text(key)
        return json.loads(data)
    except (ObjectNotFoundError, FileNotFoundError):
        return {}


def save_guild_preferences(guild_id, preferences):
    key = f"PREFERENCES/{guild_id}-preferences.json"
    client.upload_from_text(key, json.dumps(preferences))


def load_sessions_data():
    try:
        data = client.download_as_text("SESSIONS.json")
        logging.info("Successfully loaded SESSIONS.json")
        return json.loads(data)
    except (ObjectNotFoundError, FileNotFoundError):
        logging.info("SESSIONS.json not found, creating a new one.")
        return {}


def is_admin(interaction: discord.Interaction) -> bool:
    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.id == 809619070639013888
    )


async def cleanup_replays():
    replay_file_path = "replays/"
    if os.path.exists(replay_file_path):
        shutil.rmtree(replay_file_path)
        logging.info("Deleted replay folder")


@tasks.loop(seconds=45)
async def auto_logging_task():
    try:
        now_utc = datetime.now(timezone.utc).time()

        US_START = time(0, 55)
        US_END = time(7, 10)
        EU_START = time(13, 55)
        EU_END = time(22, 10)

        if US_START <= now_utc <= US_END or EU_START <= now_utc <= EU_END:
            await auto_logging()
            
    except Exception as e:
        logging.error(f"Unhandled exception in auto_logging: {e}")


async def auto_logging():
    try:
        logging.info("Running autologs")
        start_time = T.time()
        games = await fetch_games_for_user("")
        if not games:
            logging.error("No games returned from fetch_games_for_user('')")
            return

        logging.info(
            f"Matches being checked: {[x.get('sessionIdHex') for x in games]}")
        squadrons_json = client.download_as_text("SQUADRONS.json")
        squadrons_data = json.loads(squadrons_json)
        sessions_data = load_sessions_data()
        scanned_sessions = set(sessions_data.get("global", []))
        

        games_to_get_basic_data = []
        for game in games:  # gets all the matchs to run basic data on
            session_id = game.get("sessionIdHex")
            #logging.info(f"Session {session_id} is now being reviewed.")

            if session_id in scanned_sessions:
                #logging.info(f"Session {session_id} already scanned, skipping.")
                continue
            else:
                scanned_sessions.add(session_id)
                logging.info(f"Session {session_id} needs to be scanned.")
                games_to_get_basic_data.append(game)

        out = await asyncio.gather(*[
            get_basic_replay_info(game.get("sessionIdHex"))
            for game in games_to_get_basic_data
        ])
        logging.info(
            f"Finished getting basic data for {len(games_to_get_basic_data)} games."
        )

        hex_plus_guild = {}
        for game in games_to_get_basic_data:
            session_id = game.get("sessionIdHex")
            
            replay_basic_path = f"replays/0{session_id}/basic_data.json"
            try:
                with open(replay_basic_path, "r") as replay_file:
                    basic_data = json.load(replay_file)

            except Exception as e:
                logging.error(
                    f"Error reading basic replay data json for session {session_id}: {e}"
                )
                continue
                
            replay_squadrons = basic_data.get("squadrons", [])
            logging.info(
                f"Replay squadrons for session {session_id}: {replay_squadrons}"
            )
            if not replay_squadrons:
                logging.warning(
                    f"No squadrons found in replay data for session {session_id}, skipping this session."
                )
                continue

            long_clans = []
            for squadron_short in replay_squadrons:
                # Attempt Method 1: Look for a match in the JSON data.
                long_sq_name = None
                for squadron in squadrons_data.values():
                    if squadron["SQ_ShortHand_Name"] == squadron_short:
                        logging.info("Method 1 worked.")
                        long_sq_name = squadron["SQ_LongHandName"]
                        break  # Stop searching once a match is found.

                if long_sq_name:
                    long_clans.append(long_sq_name.lower())

                else:
                    clan_data = await search_for_clan(squadron_short.lower())
                    if clan_data:
                        clan_long_name = clan_data.get("long_name", squadron_short)
                        long_clans.append(clan_long_name.lower())
                    else:
                        logging.error(
                            f"Squadron '{squadron_short}' not found for session {session_id}."
                        )

            for guild in bot.guilds:
                #activated = load_active_guilds(guild.id)
                

                preferences = load_guild_preferences(guild.id)

                if not preferences:
                    continue

                squadrons_with_logs = {
                    squadron_name: squadron_prefs["Logs"]
                    for squadron_name, squadron_prefs in preferences.items()
                    if "Logs" in squadron_prefs
                }

                #logging.info(f"Logs setup for {guild.name} ({guild.id}): {squadrons_with_logs}")

                processed = False
                for squadron_name, squadron_prefs in squadrons_with_logs.items(
                ):
                    if squadron_name.lower() in long_clans:
                        if not processed:
                            logging.info(
                                f"Processing session {session_id} for guild {guild.name} ({guild.id}) with teams {replay_squadrons}"
                            )
                            # try:
                            if session_id in hex_plus_guild:
                                hex_plus_guild[session_id][1].append(
                                    (guild, squadron_prefs))
                            else:
                                hex_plus_guild[session_id] = [
                                    game, [(guild, squadron_prefs)]
                                ]
                            #     await save_replay_data(session_id, part_count=parts_count)
                            #     await process_session(bot, session_id, guild.id, squadron_prefs, mission_name, guild.name)
                            # except Exception as e:
                            #     logging.error(f"Error processing session {session_id} for guild {guild.name} ({guild.id}): {e}")
                            #     logging.error(f"{traceback.format_exc()}")

                            processed = True
                        else:
                            logging.info(
                                f"Already processed session {session_id} for guild {guild.name} ({guild.id}), skipping duplicate."
                            )

        # this has a try except block in it, so even if one fails it wont crash the entire logging process
        logging.info(f"logging replays {[game.get('sessionIdHex') for game, guilds in hex_plus_guild.values()]}")
        
        out = await asyncio.gather(*[
            save_replay_data(game.get("sessionIdHex"),
                             part_count=game.get("partsCount"))
            for game, guilds in hex_plus_guild.values()
        ])
        
        logging.info(f"FINISHED PROCESSING {len(out)} REPLAYS")

        for game, guilds in hex_plus_guild.values():
            for guild, squadron_prefs in guilds:
                try:
                    await process_session(bot, game.get("sessionIdHex"), guild.id, squadron_prefs, game.get("missionName"), guild.name, game.get("endTime"))
                except Exception as e:
                    logging.error(
                        f"Error processing session {game.get('sessionIdHex')} for guild {guild.name} ({guild.id}): {e}"
                    )
                    logging.error(f"{traceback.format_exc()}")

        sessions_data["global"] = list(scanned_sessions)
        client.upload_from_text("SESSIONS.json",
                                json.dumps(sessions_data, indent=4))
        logging.info("Global sessions data updated.")
        logging.info(f"Finished autologs in {T.time() - start_time} seconds.")

        for session_id in scanned_sessions:
            folder_path = f"replays/0{session_id}"
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                for file_name in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, file_name)
                    if os.path.isfile(file_path) and file_name.endswith(
                            ".wrpl"):
                        os.remove(file_path)

    except Exception as e:
        logging.error(f"Error occured in logs: {e}")
        logging.error(f"{traceback.format_exc()}")


@auto_logging_task.before_loop
async def before_auto_logging_task():
    await bot.wait_until_ready()


async def process_session(bot, session_id, guild_id, squadron_preferences, map_name, guild_name, timestamp):
    # Define the replay file path.
    replay_file_path = f"replays/0{session_id}/replay_data.json"

    # Attempt to load the replay data from file.
    try:
        with open(replay_file_path, "r") as replay_file:
            replay_data = json.load(replay_file)
    except FileNotFoundError:
        logging.error(f"Replay file not found for session ID {session_id}")
        return
    except json.JSONDecodeError:
        logging.error(f"Replay file for session ID {session_id} is invalid JSON")
        return

    # Extract the winning squadron.
    winner = replay_data.get("winning_team_squadron")
    if winner is None:
        logging.warning(f"Session {session_id} has a null 'winning_team_squadron'.")
        # return

    # Retrieve the list of squadrons and teams from the replay.
    squadrons = replay_data.get("squadrons", [])
    teams = replay_data.get("teams", [])
    mission = map_name  # Use the provided mission name.
    decimal_session_id = int(session_id, 16)
    replay_url = f"https://warthunder.com/en/tournament/replay/{decimal_session_id}"

    # Load SQUADRONS.json to fetch guild-specific squadron data.
    try:
        squadrons_json = client.download_as_text("SQUADRONS.json")
        squadrons_data = json.loads(squadrons_json)
    except Exception:
        logging.warning("SQUADRONS.json not found. Using empty data.")
        squadrons_data = {}

    # Get the expected squadron shortname for this guild (e.g., "EXLY").
    guild_data = squadrons_data.get(str(guild_id), {})
    guild_squadron = guild_data.get("SQ_ShortHand_Name", None)

    # Determine the losing squadron.
    if len(squadrons) >= 2:
        loser = squadrons[0] if squadrons[1] == winner else squadrons[1]
    else:
        loser = "Unknown"

    # Set the embed color based on the guild's involvement.
    if guild_squadron is None:
        embed_color = discord.Color.blue()  # No squadron set.
    elif winner == guild_squadron:
        embed_color = discord.Color.green()  # Win.
    elif loser == guild_squadron:
        embed_color = discord.Color.red()  # Loss.
    else:
        embed_color = discord.Color.purple()  # Not directly involved.

    w1 = winner
    if winner == "Unknown":  # if the winner is unknown, then set it to the other squadron that is not the 'loser'
        w1 = squadrons[0] if squadrons[1] == loser else squadrons[1]
        embed_color = discord.Color.purple()

    # Build the Discord embed.
    text_timestamp = f"<t:{timestamp}:R>"
    embed = discord.Embed(
        title=f"**{w1} vs {loser}**",
        description=f"Battle Ended: {text_timestamp}\n[Replay Link]({replay_url})",
        color=embed_color,
    )
    embed.set_footer(text="Meow :3")

    guild_features = await load_features(guild_id)
    language = guild_features.get("Language", "<English>")
    translate = LangTableReader(language)

    # Translate vehicles for each player in both teams in memory
    for team in teams:
        for player in team.get("players", []):
            if player.get("vehicle"):
                player["vehicle_new"] = translate.get_translate(player["vehicle"] + "_shop")
            else:
                logging.warning(
                    f"{player.get('nick')} did not have a vehicle, most likely a disconnect. REPLAY HEX 0{session_id}"
                )
                player["vehicle"] = "DISCONNECTED"
    
    match_details = {
        "utc_timestamp": str(timestamp),
        "session_id": str(session_id)
    }

    language = language.replace("<","")
    language = language.replace(">","")
    
    output_path = f"replays/0{session_id}/game_result-{language}.png"

    if not os.path.exists(output_path):
        await create_scoreboard(match_details, winner, teams[0], teams[1], mission, output_path)

    
    # embed.set_image(url="attachment://game_result.png")

    channel_id_str = squadron_preferences
    try:
        # Remove Discord formatting and convert to integer.
        channel_id = int(channel_id_str.strip("<#>"))
    except ValueError:
        logging.error(f"Invalid channel ID format: {channel_id_str} in guild ({guild_id})")
        return

    # Send the embed to the designated channel.
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            view = discord.ui.View()
            button = discord.ui.Button(
                label="View Replay",
                style=discord.ButtonStyle.link,
                url=replay_url
            )
            view.add_item(button)
            
            # add a button under this image with a placeholder link and placeholder text
            await channel.send(file=discord.File(output_path, filename="game_result.png"), view=view)
            
            logging.info(
                f"Embed and image sent for session {session_id} in {guild_name} ({guild_id})"
            )
        else:
            logging.warning(f"Channel ID {channel_id} not found in {guild_name} ({guild_id})")
    except Exception as e:
        logging.error(
            f"Failed to send embed for session {session_id} in {guild_name} ({guild_id}): {e}"
        )



async def update_billing(server_id, server_name, user_name, user_id,
                         cmd_timestamp):
    try:
        raw_data = client.download_as_text("BILLING.json")
        data = json.loads(raw_data) if raw_data else {}
        logging.info("Successfully loaded BILLING.json")
    except (ObjectNotFoundError, FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(
            f"BILLING.json not found or invalid, creating a new one. Error: {e}"
        )
        data = {}

    server_id = str(server_id)  # Ensure server_id is a string
    if server_id not in data:
        logging.info(f"Server ID {server_id} not found, creating new entry.")
        data[server_id] = {
            "server_name": server_name,
            "use_total": 0,
            "uses": []
        }
    else:
        logging.info(f"Server ID {server_id} found, appending new entry.")

    # Increment use_total count
    data[server_id]["use_total"] += 1

    # Append the new use entry
    new_entry = {
        "timestamp": cmd_timestamp,
        "user_name": user_name,
        "user_id": user_id
    }
    data[server_id]["uses"].append(new_entry)

    #logging.info(f"Final data structure before saving: {json.dumps(data, indent=4)}")

    # Save the updated data
    client.upload_from_text("BILLING.json", json.dumps(data, indent=4))
    logging.info(
        f"Logged billing entry for {server_name} ({server_id}) - User: {user_name} ({user_id}) at {cmd_timestamp}"
    )


@bot.tree.command(name='find-comp',
                  description='Find the last known comp for a given team')
@app_commands.describe(username='The username of an enemy player')
async def find_comp(interaction: discord.Interaction, username: str):
    await interaction.response.defer()

    # Get command invocation details
    user = interaction.user
    user_name = user.name
    user_id = user.id

    guild = interaction.guild
    server_name = guild.name
    server_id = guild.id

    cmd_timestamp = DT.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    logging.info(f"FIND-COMP used by {user_name} (ID: {user_id}) in server '{server_name}' (ID: {server_id}) for username '{username}'")

    try:
        # Fetch games for the given username
        games = await fetch_games_for_user(username)
        if not games:
            await interaction.followup.send(f"No games found for user `{username}`.")
            return

        game1 = games[0]
        game2 = games[1]
        current_unix_time = int(T.time())
        end_time_second = game2.get("endTime")
        time_diff = current_unix_time - end_time_second
        """
        If the 2nd game is older than half an hour, then choose the first game (A)
        If its younger than 30 minutes, check if its fully parsed or not (B)
        If it is not fully parsed, we might as well download and parse the first game anyways (C)
        """

        if time_diff > 1800:  # (A)
            selected_game = game1
            footer = "Meow :3"
            logging.info("(COMP) selected the first game for download.")

        else:
            logging.info("(COMP) checking if second game is fully parsed.")
            session_id = game2.get('sessionIdHex', "Error")
            replay_file_path = f"replays/0{session_id}/replay_data.json"

            if os.path.exists(replay_file_path):  # (B)
                logging.info(
                    "(COMP) second game is fully parsed, sending now.")
                selected_game = game2
                footer = "Instant"

            else:  # (C)
                logging.info(
                    "(COMP) second game isnt fully parsed, using first game.")
                selected_game = game1
                footer = "Meow :3"

        for game in [selected_game]:
            session_id = game.get('sessionIdHex', "Error")
            try:
                mission = game.get("missionName", "Error")
                timestamp = game.get("endTime", "Error")
                utc_timestamp = timestamp
                parts_count = game.get("partsCount")
                time_diff = current_unix_time - timestamp

                if time_diff > 1800:
                    timestamp = f"<t:{timestamp}:R> :warning:"
                else:
                    timestamp = f"<t:{timestamp}:R>"

                replay_file_path = f"replays/0{session_id}/replay_data.json"

                if not os.path.exists(replay_file_path):
                    comp = True
                    logging.info(
                        "(COMP) Replay didn't exist, downloading now...")
                    await save_replay_data(session_id,
                                           comp,
                                           part_count=parts_count)

                try:
                    with open(replay_file_path, "r") as replay_file:
                        replay_data = json.load(replay_file)

                except FileNotFoundError:
                    logging.error(
                        f"(COMP) Replay file not found for session ID {session_id}"
                    )
                    continue  # Try the next game

                squadrons = replay_data.get("squadrons", [])
                #weather = replay_data.get("weather", "Unknown")
                #time_of_day = replay_data.get("time_of_day", "Unknown")
                winner = replay_data.get("winning_team_squadron")
                teams = replay_data.get("teams", [])

                decimal_session_id = int(session_id, 16)
                replay_url = f"https://warthunder.com/en/tournament/replay/{decimal_session_id}"

                # Create the embed
                embed = discord.Embed(
                    title=f"**{squadrons[0]} vs {squadrons[1]}**",
                    description=
                    f"Battle Ended: {timestamp}\n[Replay Link]({replay_url})",
                    color=discord.Color.gold(),
                )

                embed.set_footer(text=footer)

                guild_features = await load_features(guild.id)
                logging.info(guild_features)
                language = guild_features.get("Language", "<English>")
                translate = LangTableReader(language)


                # Translate vehicles for each player in both teams in memory
                for team in teams:
                    for player in team.get("players", []):
                        if player.get("vehicle"):
                            player["vehicle_new"] = translate.get_translate(player["vehicle"] + "_shop")
                        else:
                            logging.warning(
                                f"{player.get('nick')} did not have a vehicle, most likely a disconnect. REPLAY HEX 0{session_id}"
                            )
                            player["vehicle"] = "DISCONNECTED"

                # Generate the scoreboard screenshot
                output_path = f"replays/0{session_id}/game_result.png"

                match_details = {
                    "utc_timestamp": str(utc_timestamp),
                    "session_id": str(session_id)
                }

                language = language.replace("<","")
                language = language.replace(">","")

                output_path = f"replays/0{session_id}/game_result-{language}.png"

                if not os.path.exists(output_path):
                    await create_scoreboard(match_details, winner, teams[0], teams[1], mission, output_path)

                # Attach the screenshot to the embed by setting it as the embed image.
                # The filename ("game_result.png") must match the one in the file attachment.
                embed.set_image(url="attachment://game_result.png")
                
                try:
                    # Send the embed along with the screenshot file attached.
                    await interaction.followup.send(
                        embed=embed,file=discord.File(output_path, filename="game_result.png")
                    )

                    try:
                        await update_billing(server_id, server_name, user_name, user_id, cmd_timestamp)
                        return  # Exit after a successful bill

                    except Exception as e:
                        logging.error(
                            f"(COMP) Failed to bill {server_name} ({server_id}) for session {session_id}: {e}"
                        )

                except Exception as e:
                    logging.error(
                        f"(COMP) Failed to send embed for session {session_id}: {e}"
                    )
                    

            except Exception as e:
                logging.error(
                    f"(COMP) An error occurred while processing session ID {session_id}: {e}"
                )
                logging.error(f"(COMP) Traceback Error: {traceback.format_exc()}")
                #continue  # Try the next game

        # If an uncaught exception happened, it ends up here
        await interaction.followup.send("An error occured, if needed try again with a different username? Contact not_so_toothless for help.")

    except Exception as e:
        logging.error(
            f"(COMP) An error occurred in the find-comp command: {e}")
        await interaction.followup.send(
            "An error occurred while processing the command. Please try again."
        )


@bot.tree.command(name="alarm", description="Set an alarm to monitor squadron changes")
@app_commands.describe(
    type="The type of alarm (Points, Logs)",
    channel_id="Type '#' and select the channel from the list",
    squadron_name="The SHORT name of the squadron to monitor"
)
@app_commands.check(is_admin)
async def alarm(
    interaction: discord.Interaction,
    type: str,
    channel_id: str,
    squadron_name: str
):
    await interaction.response.defer()

    if type not in ("Logs", "Points"):
        await interaction.response.send_message(
            "Type can only be set to Logs or Points", ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    guild_name = interaction.guild.id
    key = f"PREFERENCES/{guild_id}-preferences.json"
    alarm_type = type.title()

    # load or init preferences
    try:
        data = client.download_as_text(key)
        preferences = json.loads(data)
    except ObjectNotFoundError:
        preferences = {}

    # resolve full squadron name
    clan_data = await search_for_clan(squadron_name.lower())
    if not clan_data:
        await interaction.followup.send("Squadron not found.", ephemeral=True)
        return
    long_name = clan_data["long_name"]

    # get‑or‑create the dict for this squadron, then set/overwrite the channel for this alarm type
    # essentially will replace the channel for a squadron already set
    preferences.setdefault(long_name, {})[alarm_type] = channel_id

    # save and confirm
    client.upload_from_text(key, json.dumps(preferences))
    await interaction.followup.send(f"{alarm_type} alarm for {squadron_name} set to channel {channel_id}.", ephemeral=True)

    logging.info(f"{guild_name} ({guild_id}) is now logging {squadron_name} in channel ID {channel_id}")


@alarm.error
async def alarm_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)


@bot.tree.command(
    name="quick-log",
    description="Quickly set a ‘Logs’ alarm for this squadron in this channel"
)
@app_commands.describe(
    sq_name="The SHORT name of the squadron to monitor",
    type="Put points here to enable point tracking"
)
@app_commands.check(is_admin)
async def quick_log(interaction: discord.Interaction, sq_name: str, type: str = "Logs"):
    type = type.title()
    
    if type not in ("Logs", "Points"):
        await interaction.response.send_message(
            "Type can only be set to Logs or Points", ephemeral=True
        )
        return
        
    # defer so we can do I/O
    await interaction.response.defer()

    guild_id = interaction.guild.id
    guild_name = interaction.guild.name
    key = f"PREFERENCES/{guild_id}-preferences.json"

    # load existing prefs or start fresh
    try:
        data = client.download_as_text(key)
        preferences = json.loads(data)
    except ObjectNotFoundError:
        preferences = {}

    # resolve the squadron
    clan_data = await search_for_clan(sq_name.lower())
    if not clan_data:
        await interaction.followup.send("Squadron not found.", ephemeral=True)
        return

    long_name = clan_data.get("long_name")
    channel_id = interaction.channel.id
    # get‑or‑create the dict for this squadron, then set/overwrite the channel for this alarm type
    # essentially will replace the channel for a squadron already set
    preferences.setdefault(long_name, {})[type] = str(channel_id)

    # save it back
    client.upload_from_text(key, json.dumps(preferences))

    await interaction.followup.send(
        f"{type} alarm for {sq_name} set to this channel.",
        ephemeral=True
    )
    logging.info(f"{guild_name} ({guild_id}) is now logging {sq_name} in channel ID {channel_id}")


@quick_log.error
async def quick_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)



@bot.tree.command(name="sq-info", description="Fetch information about a squadron")
@app_commands.describe(
    squadron="The short name of the squadron to fetch information about",
    type=
    "The type of information to display: members, or points"
)
async def sq_info(interaction: discord.Interaction,
                  squadron: str = "",
                  type: str = ""):
    await interaction.response.defer(ephemeral=False)

    filename = "SQUADRONS.json"
    squadrons_json = client.download_as_text(filename)
    squadrons = json.loads(squadrons_json)
    guild_id = str(interaction.guild_id)

    if not squadron:
        if guild_id in squadrons:
            squadron_name = squadrons[guild_id]["SQ_LongHandName"]
        else:
            embed = discord.Embed(
                title="Error",
                description=
                "No squadron specified and no squadron is set for this server.",
                color=discord.Color.red())
            embed.set_footer(text="Meow :3")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
    else:
        clan_data = await search_for_clan(squadron.lower())
        if not clan_data:
            await interaction.followup.send("Squadron not found.", ephemeral=True)
            return

        squadron_name = clan_data.get("long_name")
    embed = await fetch_squadron_info(squadron_name, type)

    if embed:
        embed.set_footer(text="Meow :3")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send("Failed to fetch squadron info.", ephemeral=True)


@bot.tree.command(name='stat',
                  description='Get the ThunderSkill stats URL for a user')
@app_commands.describe(username='The username to get stats for')
async def stat(interaction: discord.Interaction, username: str):
    url = f"https://thunderskill.com/en/stat/{username}"
    await interaction.response.send_message(url, ephemeral=False)


active_guessing_games = {}  # Dictionary to keep track of active guessing games by channel ID, maybe this is a bad idea?


def update_leaderboard(guild_id, user_id, points):
    filename = f"{guild_id}-game-rank.json"
    leaderboard = {}

    # Download the leaderboard file
    try:
        leaderboard_json = client.download_as_text(filename)
        leaderboard = json.loads(leaderboard_json)
    except Exception:
        logging.warning(
            f"Leaderboard file for guild {guild_id} not found. Creating a new one."
        )

    user_id_str = str(user_id)

    if user_id_str in leaderboard:
        leaderboard[user_id_str] += points
    else:
        leaderboard[user_id_str] = points

    # Upload the updated leaderboard file
    client.upload_from_text(filename, json.dumps(leaderboard))


@bot.tree.command(name='time-now', description='Get the current UTC and local time')
async def time_now(interaction: discord.Interaction):
    utc_time = DT.datetime.utcnow().strftime('%I:%M %p')
    timestamp = int(DT.datetime.utcnow().timestamp())

    embed = discord.Embed(
        title="Current UTC and local Time",
        description=
        f"**UTC Time:** {utc_time}\n**Local Time:** <t:{timestamp}:t>",
        color=discord.Color.blue())
    embed.set_footer(text="Meow :3")

    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name='set-squadron', description='Set the squadron tag for this server')
@app_commands.describe(abbreviated_name='The short name of the squadron to set')
async def set_squadron(interaction: Interaction, abbreviated_name: str):
    await interaction.response.defer(ephemeral=True)

    filename = "SQUADRONS.json"
    # load or init
    try:
        data = client.download_as_text(filename)
        squadrons = json.loads(data)
    except Exception:
        squadrons = {}

    guild_id = str(interaction.guild_id)

    # sanitize and fetch new clan data
    new_short = re.sub(r'\W+', '', abbreviated_name)
    clan_data = await search_for_clan(new_short.lower())
    if not clan_data:
        return await interaction.followup.send(
            embed=Embed(title="Error", description=f"Squadron `{new_short}` not found.", color=Color.red())
        )
    new_long = clan_data["long_name"]

    # if a different squadron already set, prompt confirmation
    if guild_id in squadrons and squadrons[guild_id]['SQ_ShortHand_Name'] != new_short:
        old_long = squadrons[guild_id]['SQ_LongHandName']

        class ConfirmSwapView(View):
            def __init__(self):
                super().__init__(timeout=60)

            @button(label="Yes, swap it", style=ButtonStyle.green)
            async def confirm(self, interaction: Interaction, button: discord.ui.Button):
                # overwrite the squadron
                squadrons[guild_id] = {
                    "SQ_ShortHand_Name": new_short,
                    "SQ_LongHandName": new_long
                }
                client.upload_from_text(filename, json.dumps(squadrons))

                embed = Embed(
                    title="✅ Squadron Swapped",
                    description=f"Replaced **{old_long}** with **{new_long}** for this server.",
                    color=Color.green()
                )
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()

            @button(label="No, keep the old one", style=ButtonStyle.red)
            async def cancel(self, interaction: Interaction, button: discord.ui.Button):
                await interaction.response.edit_message(
                    content="❌ Squadron change cancelled.", embed=None, view=None
                )
                self.stop()

        view = ConfirmSwapView()
        embed = Embed(
            title="⚠️ Squadron Already Set",
            description=(
                f"This server is currently set to **{old_long}**.\n"
                f"Swap it to **{new_long}**?"
            ),
            color=Color.gold()
        )
        return await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # otherwise, just set it
    squadrons[guild_id] = {
        "SQ_ShortHand_Name": new_short,
        "SQ_LongHandName": new_long
    }
    client.upload_from_text(filename, json.dumps(squadrons))

    embed = Embed(
        title="✅ Squadron Set",
        description=f"Squadron **{new_long}** has been set for this server.",
        color=Color.green()
    )
    embed.add_field(name="Short Name", value=new_short, inline=True)
    embed.add_field(name="Long Name", value=new_long, inline=True)
    embed.set_footer(text="Meow :3")
    await interaction.followup.send(embed=embed, ephemeral=False)


@bot.tree.command(name='top', description='Get the top 20 squadrons with detailed stats')
async def top(interaction: discord.Interaction):
    await interaction.response.defer()

    squadron_data = await get_top_20()
    if not squadron_data:
        await interaction.followup.send("Failed to retrieve squadron data.", ephemeral=True)
        return

    embed = discord.Embed(title="**Top 20 Squadrons**", color=discord.Color.purple())

    for idx, squadron in enumerate(squadron_data, start=1):
        ground_kills = squadron.get("g_kills", 0)
        air_kills = squadron.get("a_kills", 0)
        total_kills = ground_kills + air_kills
        deaths = squadron.get("deaths", 1)  # Avoid division by zero
        kd_ratio = round(total_kills / deaths, 2) if deaths else "N/A"

        # Calculate win rate (ensure battles is not zero to avoid division errors)
        wins = squadron.get("wins", 0)
        battles = squadron.get("battles", 0)
        win_rate = round((wins / battles) * 100, 2) if battles else "N/A"

        playtime_minutes = squadron.get("playtime", 0)
        days = playtime_minutes // 1440
        hours = (playtime_minutes % 1440) // 60
        minutes = playtime_minutes % 60
        formatted_playtime = f"{days}d {hours}h {minutes}m"

        embed.add_field(
            name=f"**{idx} - {squadron['tag']}**",
            value=(
                f"**Squadron Score:** {squadron.get('clanrating', 'N/A')}\n"
                f"**Air Kills:** {air_kills}\n"
                f"**Ground Kills:** {ground_kills}\n"
                f"**Deaths:** {deaths}\n"
                f"**K/D:** {kd_ratio}\n"
                f"**Win Rate:** {win_rate if win_rate == 'N/A' else str(win_rate) + '%'}\n"
                f"**Playtime:** {formatted_playtime}\n"
                "\u200b"  # Adds spacing
            ),
            inline=True  # Each squadron appears on a new line
        )

    embed.set_footer(text="Meow :3")
    await interaction.followup.send(embed=embed, ephemeral=False)


async def load_features(guild_id):
    key = f"FEATURES/{guild_id}-features.json"
    try:
        data = client.download_as_text(key)
        return json.loads(data)

    except (ObjectNotFoundError, FileNotFoundError):
        # If file doesn't exist, create it with default values
        features = {"Translate": "False", "Language": "<English>"}
        client.upload_from_text(key, json.dumps(features))
        return features


async def save_features(guild_id, features):
    key = f"FEATURES/{guild_id}-features.json"
    client.upload_from_text(key, json.dumps(features))


@bot.tree.command(name="toggle", description="Toggle a feature for the server (Currently supports 'Translate')")
@app_commands.describe(feature="Feature to toggle (only 'Translate' supported)")
@app_commands.check(is_admin)
async def toggle(interaction: discord.Interaction, feature: str):
    await interaction.response.defer()

    if feature.lower() != "translate":
        await interaction.followup.send("Invalid feature. Only 'Translate' can be toggled.", ephemeral=True)
        return

    guild_id = interaction.guild.id
    features = await load_features(guild_id)

    # Set Translate explicitly to True or False
    features["Translate"] = "True" if features["Translate"] == "False" else "False"
    await save_features(guild_id, features)
    await interaction.followup.send(f"Translate feature set to {features['Translate']}.", ephemeral=True)

@toggle.error
async def toggle_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

class LanguageSelect(discord.ui.Select):
    def __init__(self):
        # Mapping of displayed language names to canonical stored values
        self.language_mapping = {
            "English": "<English>",
            "Français": "<French>",
            "Italiano": "<Italian>",
            "Deutsch": "<German>",
            "Español": "<Spanish>",
            "Русский": "<Russian>",
            "Polski": "<Polish>",
            "Čeština": "<Czech>",
            "Türkçe": "<Turkish>",
            "中文": "<Chinese>",
            "日本語": "<Japanese>",
            "Português": "<Portuguese>",
            "Українська": "<Ukrainian>",
            "Српски": "<Serbian>",
            "Magyar": "<Hungarian>",
            "한국어": "<Korean>",
            "Беларуская": "<Belarusian>",
            "Română": "<Romanian>",
            "繁體中文": "<TChinese>"
        }

        options = [
            discord.SelectOption(label=label, value=label)
            for label in self.language_mapping
        ]

        super().__init__(
            placeholder="Choose your server language", 
            min_values=1, 
            max_values=1, 
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        guild_name = interaction.guild.name
        features = await load_features(guild_id)

        selected_display = self.values[0]
        canonical_value = self.language_mapping.get(selected_display, f"<{selected_display}>")

        features["Language"] = canonical_value
        await save_features(guild_id, features)

        await interaction.response.send_message(f"Language set to {selected_display}.", ephemeral=True)
        logging.info(f"Guild {guild_name} ({guild_id}) set their language to {canonical_value}")

class LanguageView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(LanguageSelect())

@bot.tree.command(name="languages",description="Change the bot's language.")
@app_commands.check(is_admin)
async def languages(interaction: discord.Interaction):
    view = LanguageView()
    await interaction.response.send_message("Please select your server language:", view=view, ephemeral=True)

@languages.error
async def languages_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)



# Dictionary mapping flag emojis to uppercase, allowed language codes
LANGUAGE_MAP = {
    "🇷🇺": "RU",        # Russian
    "🇺🇸": "EN-US",     # English (US)
    "🇬🇧": "EN-GB",     # English (UK)
    "🇪🇸": "ES",        # Spanish
    "🇫🇷": "FR",        # French
    "🇩🇪": "DE",        # German
    "🇨🇳": "ZH-HANS",   # Chinese (Simplified)
    "🇯🇵": "JA",        # Japanese
    "🇰🇷": "KO",        # Korean
    "🇮🇹": "IT",        # Italian
    "🇵🇹": "PT-PT",     # Portuguese (Portugal)
    "🇧🇷": "PT-BR",     # Portuguese (Brazil)
    "🇵🇱": "PL",        # Polish
    "🇱🇹": "LT",        # Lithuanian
    "🇱🇻": "LV",        # Latvian
    "🇪🇪": "ET",        # Estonian
    "🇩🇰": "DA",        # Danish
    "🇫🇮": "FI",        # Finnish
    "🇮🇩": "ID",        # Indonesian
    "🇳🇴": "NB",        # Norwegian
    "🇳🇱": "NL",        # Dutch
    "🇸🇪": "SV",        # Swedish
    "🇺🇦": "UK",        # Ukrainian
    "🇨🇿": "CS",        # Czech
    "🇸🇰": "SK",        # Slovak
    "🇸🇮": "SL",        # Slovenian
    "🇷🇴": "RO",        # Romanian
    "🇧🇬": "BG",        # Bulgarian
    "🇬🇷": "EL",        # Greek
    "🇭🇺": "HU",        # Hungarian
    "🇸🇦": "AR",        # Arabic
    "🇹🇷": "TR",        # Turkish
    "🏳️‍🌈": "PL"        # Polish (gay)
}


DEEPL_API_KEY = os.environ.get("DEEPL_KEY")
translator = deepl.Translator(DEEPL_API_KEY)

def sanitize_text(text: str, message: discord.Message) -> str:
    text = text.replace("@everyone", "EVERYONE")
    text = text.replace("@here", "HERE")

    # Replace user mentions with "USERNAME"
    for user in message.mentions:
        text = text.replace(user.mention, user.display_name)

    # Replace role mentions with "ROLENAME"
    for role in message.role_mentions:
        text = text.replace(role.mention, role.name)

    return text


def perform_translation(text: str, target_language: str) -> str:
    result = translator.translate_text(text, target_lang=target_language.upper())
    return result.text


translated_messages: set[int] = set()

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # ignore bot reactions
    if payload.user_id == bot.user.id:
        return

    # dedupe: skip if we’ve just translated this message
    if payload.message_id in translated_messages:
        return

    emoji = str(payload.emoji)
    if emoji not in LANGUAGE_MAP:
        return

    features = await load_features(payload.guild_id)
    if not features or features.get("Translate") != "True":
        return

    # fetch the channel & message
    channel = bot.get_channel(payload.channel_id) or await bot.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    # sanitize & translate
    text = sanitize_text(message.content, message)
    translated_text = perform_translation(text, LANGUAGE_MAP[emoji])
    if not translated_text:
        await channel.send(f"Translation failed for: {emoji}", delete_after=5)
        return

    # remove the user’s reaction
    user = bot.get_user(payload.user_id) or await bot.fetch_user(payload.user_id)
    with suppress(discord.Forbidden):
        await message.remove_reaction(payload.emoji, user)

    # send translation & schedule its deletion
    username = escape_markdown(message.author.display_name)
    sent = await channel.send(f"**{username} - ({emoji}):** {translated_text}")
    await sent.delete(delay=60)

    # record that we’ve translated this message
    translated_messages.add(payload.message_id)

    # schedule ID removal after 60s
    async def _clear_id(msg_id: int):
        await asyncio.sleep(60)
        translated_messages.discard(msg_id)

    asyncio.create_task(_clear_id(payload.message_id))


async def return_latest_battle():
    # Maybe one day I can get this to work again, but past the new rate limits, its unlikely.
    return "meow"


@bot.tree.command(
    name="track",
    description="Track a certain squadron to see when they last played SQB")
@app_commands.describe(
    squadron_short_name="Short name of the squadron to track")
async def track_squadron(interaction: discord.Interaction,
                         squadron_short_name: str):
    await interaction.response.defer()
    logging.info("Running /track")

    clan_data = await search_for_clan(squadron_short_name.lower())
    if not clan_data:
        await interaction.followup.send("Squadron not found.", ephemeral=True)
        return

    clan_tag = clan_data.get("tag")
    points = int(clan_data.get("clanrating"))
    ground_kills = int(clan_data.get("g_kills"))
    air_kills = int(clan_data.get("a_kills"))
    deaths = int(clan_data.get("deaths"))
    battles = int(clan_data.get("battles"))
    wins = int(clan_data.get("wins"))
    members = clan_data.get("members")

    total_kills = ground_kills + air_kills
    kd_ratio = total_kills / deaths if deaths > 0 else total_kills
    kd_ratio_percentage = f"{kd_ratio:.2f}"

    losses = battles - wins
    win_rate = (wins / battles) * 100 if battles > 0 else 0
    win_rate_percentage = f"{win_rate:.2f}%"

    embed = discord.Embed(title=f"**{clan_tag}**", color=discord.Color.green())

    embed.add_field(name="Points", value=points, inline=True)
    embed.add_field(name="Members", value=members, inline=True)
    embed.add_field(name="Win Rate", value=win_rate_percentage, inline=True)

    embed.add_field(name="Battles", value=battles, inline=True)
    embed.add_field(name="Wins", value=wins, inline=True)
    embed.add_field(name="Losses", value=losses, inline=True)

    embed.add_field(name="Total Kills", value=total_kills, inline=True)
    embed.add_field(name="Ground Kills", value=ground_kills, inline=True)
    embed.add_field(name="Air Kills", value=air_kills, inline=True)

    embed.add_field(name="Deaths", value=deaths, inline=True)
    embed.add_field(name="KD Ratio", value=kd_ratio_percentage, inline=True)

    embed.set_footer(text="Meow :3")
    await interaction.followup.send(embed=embed, ephemeral=False)


class NotificationTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Logs",description="Manage Logs notifications"),
            discord.SelectOption(label="Points",description="Manage Points notifications")
        ]
        super().__init__(placeholder="Select notification type",
                         min_values=1,
                         max_values=1,
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        notif_type = self.values[0]
        # Proceed to Step 2: Squadron selection.
        view = create_squadron_select_view(interaction.guild.id, notif_type)
        await interaction.response.send_message(
            f"Selected **{notif_type}**. Now choose the squadron to manage:",
            view=view,
            ephemeral=True)


class NotificationManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(NotificationTypeSelect())


# Basic (non-paginated) squadron dropdown (if 25 or fewer squadrons)
class SquadronSelect(discord.ui.Select):
    def __init__(self, guild_id, notif_type, preferences):
        self.guild_id = guild_id
        self.notif_type = notif_type
        options = []
        # List squadrons that have a setting for the chosen notification type.
        for squadron, settings in preferences.items():
            if notif_type in settings:
                channel_val = settings[notif_type]
                state = "Disabled" if channel_val.startswith(
                    "<#DISABLED-") else "Enabled"
                options.append(
                    discord.SelectOption(
                        label=squadron, description=f"{state}: {channel_val}"))
        if not options:
            options.append(
                discord.SelectOption(label="None",
                                     description="No squadrons configured",
                                     value="none"))
        super().__init__(placeholder="Select a squadron",
                         min_values=1,
                         max_values=1,
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_squadron = self.values[0]
        if selected_squadron == "none":
            await interaction.response.send_message(
                "No squadron available for this notification type.",
                ephemeral=True)
            return

        # Retrieve the current channel value for the selected notification type.
        preferences = load_guild_preferences(self.guild_id)
        squadron_settings = preferences.get(selected_squadron, {})
        channel_value = squadron_settings.get(self.notif_type,
                                              "Not configured")
        if channel_value != "Not configured":
            # Check if the value is wrapped in <#...>
            if channel_value.startswith("<#") and channel_value.endswith(">"):
                channel_id_str = channel_value[2:-1]
            else:
                channel_id_str = channel_value
            # Remove "DISABLED-" if present.
            if channel_id_str.startswith("DISABLED-"):
                channel_id_str = channel_id_str[len("DISABLED-"):]
            try:
                channel_id = int(channel_id_str)
                channel = interaction.guild.get_channel(channel_id)
                channel_name = channel.name if channel else "Unknown"
            except ValueError:
                channel_name = "Unknown"
        else:
            channel_name = "Not configured"

        # Proceed to Step 3: Display toggle and change channel buttons.
        view = ToggleView(self.guild_id, self.notif_type, selected_squadron)
        await interaction.response.send_message(
            f"Managing **{self.notif_type}** for squadron **{selected_squadron}** in channel **{channel_name}**.",
            view=view,
            ephemeral=True)


# New classes for paginated squadron selection (> 25 squadrons, somehow.)
class PaginatedSquadronSelect(discord.ui.Select):
    def __init__(self, guild_id, notif_type, squadron_list, page=0):
        self.guild_id = guild_id
        self.notif_type = notif_type
        self.squadron_list = squadron_list  # List of tuples: (squadron, settings)
        self.page = page
        options = self.get_options(page)
        super().__init__(placeholder=f"Select a squadron (Page {page+1})",
                         min_values=1,
                         max_values=1,
                         options=options)

    def get_options(self, page):
        start = page * 25
        end = start + 25
        options = []
        for squadron, settings in self.squadron_list[start:end]:
            channel_val = settings[self.notif_type]
            state = "Disabled" if channel_val.startswith(
                "<#DISABLED-") else "Enabled"
            options.append(
                discord.SelectOption(label=squadron,
                                     description=f"{state}: {channel_val}"))
        if not options:
            options.append(
                discord.SelectOption(label="None",
                                     description="No squadrons configured",
                                     value="none"))
        return options

    async def callback(self, interaction: discord.Interaction):
        selected_squadron = self.values[0]
        if selected_squadron == "none":
            await interaction.response.send_message(
                "No squadron available for this notification type.",
                ephemeral=True)
            return

        preferences = load_guild_preferences(self.guild_id)
        squadron_settings = preferences.get(selected_squadron, {})
        channel_value = squadron_settings.get(self.notif_type,
                                              "Not configured")
        if channel_value != "Not configured":
            # Check if the value is wrapped in <#...>
            if channel_value.startswith("<#") and channel_value.endswith(">"):
                channel_id_str = channel_value[2:-1]
            else:
                channel_id_str = channel_value
            # Remove "DISABLED-" if present.
            if channel_id_str.startswith("DISABLED-"):
                channel_id_str = channel_id_str[len("DISABLED-"):]
            try:
                channel_id = int(channel_id_str)
                channel = interaction.guild.get_channel(channel_id)
                channel_name = channel.name if channel else "Unknown"
            except ValueError:
                channel_name = "Unknown"
        else:
            channel_name = "Not configured"

        view = ToggleView(self.guild_id, self.notif_type, selected_squadron)
        await interaction.response.send_message(
            f"Managing **{self.notif_type}** for squadron **{selected_squadron}** in channel **{channel_name}**.",
            view=view,
            ephemeral=True)


class PrevPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Previous", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: PaginatedSquadronSelectView = self.view
        if view.page > 0:
            view.page -= 1
            view.select.page = view.page
            view.select.options = view.select.get_options(view.page)
            view.select.placeholder = f"Select a squadron (Page {view.page+1})"
        await interaction.response.edit_message(view=view)


class NextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Next", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: PaginatedSquadronSelectView = self.view
        if view.page < view.total_pages - 1:
            view.page += 1
            view.select.page = view.page
            view.select.options = view.select.get_options(view.page)
            view.select.placeholder = f"Select a squadron (Page {view.page+1})"
        await interaction.response.edit_message(view=view)


class PaginatedSquadronSelectView(discord.ui.View):
    def __init__(self, guild_id, notif_type, squadron_list, page=0):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.notif_type = notif_type
        self.squadron_list = squadron_list  # List of tuples: (squadron, settings)
        self.page = page
        self.total_pages = math.ceil(len(squadron_list) / 25)
        self.select = PaginatedSquadronSelect(guild_id, notif_type,
                                              squadron_list, page)
        self.add_item(self.select)
        self.add_item(PrevPageButton())
        self.add_item(NextPageButton())


def create_squadron_select_view(guild_id, notif_type):
    """Return a View with either a paginated select or a basic select, based on number of squadrons."""
    preferences = load_guild_preferences(guild_id)
    squadron_list = []
    for squadron, settings in preferences.items():
        if notif_type in settings:
            squadron_list.append((squadron, settings))
    if len(squadron_list) > 25:
        return PaginatedSquadronSelectView(guild_id, notif_type, squadron_list)
    else:
        view = discord.ui.View(timeout=180)
        view.add_item(SquadronSelect(guild_id, notif_type, preferences))
        return view


class ToggleButton(discord.ui.Button):

    def __init__(self, guild_id, notif_type, squadron, channel_value):
        # Label reflects the current state.
        label = "Enable" if channel_value.startswith(
            "<#DISABLED-") else "Disable"
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.guild_id = guild_id
        self.notif_type = notif_type
        self.squadron = squadron

    async def callback(self, interaction: discord.Interaction):
        preferences = load_guild_preferences(self.guild_id)
        squadron_settings = preferences.get(self.squadron, {})
        current_value = squadron_settings.get(self.notif_type)
        if not current_value:
            await interaction.response.send_message("Configuration not found.",
                                                    ephemeral=True)
            return

        # Toggle by adding or removing "DISABLED-"
        if current_value.startswith("<#DISABLED-"):
            new_value = "<#" + current_value[len("<#DISABLED-"):]
        else:
            new_value = current_value.replace("<#", "<#DISABLED-", 1)
        preferences[self.squadron][self.notif_type] = new_value
        save_guild_preferences(self.guild_id, preferences)

        self.label = "Enable" if new_value.startswith(
            "<#DISABLED-") else "Disable"
        await interaction.response.send_message(
            f"{self.notif_type} for **{self.squadron}** is now " +
            ("disabled."
             if new_value.startswith("<#DISABLED-") else "enabled."),
            ephemeral=True)
        await interaction.edit_original_response(view=self.view)


class ChangeChannelButton(discord.ui.Button):

    def __init__(self, guild_id, notif_type, squadron):
        super().__init__(label="Change Channel",
                         style=discord.ButtonStyle.secondary)
        self.guild_id = guild_id
        self.notif_type = notif_type
        self.squadron = squadron

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        # If there are more than 25 channels, use the paginated view.
        if len(guild.text_channels) > 25:
            view = PaginatedChannelSelectView(guild, self.squadron,
                                              self.notif_type)
        else:
            view = ChannelSelectView(guild, self.notif_type, self.squadron)
        await interaction.response.send_message("Select a new channel:",
                                                view=view,
                                                ephemeral=True)


# The existing ChannelSelect view (for servers with 25 or fewer text channels)
class ChannelSelect(discord.ui.Select):
    def __init__(self, guild, notif_type, squadron):
        self.notif_type = notif_type
        self.squadron = squadron
        options = []
        for channel in guild.text_channels:
            options.append(
                discord.SelectOption(label=channel.name,
                                     value=str(channel.id)))
        super().__init__(placeholder="Select a channel",
                         min_values=1,
                         max_values=1,
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_channel_id = self.values[0]
        new_value = f"<#{selected_channel_id}>"
        preferences = load_guild_preferences(interaction.guild.id)
        if self.squadron in preferences and self.notif_type in preferences[
                self.squadron]:
            preferences[self.squadron][self.notif_type] = new_value
            save_guild_preferences(interaction.guild.id, preferences)
            await interaction.response.send_message(
                f"Updated {self.notif_type} for **{self.squadron}** to {new_value}",
                ephemeral=True)
        else:
            await interaction.response.send_message("Configuration not found.",
                                                    ephemeral=True)


class ChannelSelectView(discord.ui.View):
    def __init__(self, guild, notif_type, squadron):
        super().__init__(timeout=180)
        self.add_item(ChannelSelect(guild, notif_type, squadron))


class ToggleView(discord.ui.View):
    def __init__(self, guild_id, notif_type, squadron):
        super().__init__(timeout=180)
        preferences = load_guild_preferences(guild_id)
        channel_value = preferences.get(squadron,
                                        {}).get(notif_type, "Not configured")
        self.add_item(
            ToggleButton(guild_id, notif_type, squadron, channel_value))
        self.add_item(ChangeChannelButton(guild_id, notif_type, squadron))


# Paginated select menu for channels.
class PaginatedChannelSelect(discord.ui.Select):
    def __init__(self, guild, squadron, notif_type, page=0):
        self.guild = guild
        self.squadron = squadron
        self.notif_type = notif_type
        self.page = page
        self.channels = list(guild.text_channels)
        options = self.get_options(page)
        super().__init__(placeholder=f"Select a channel (Page {page+1})",
                         min_values=1,
                         max_values=1,
                         options=options)

    def get_options(self, page):
        start = page * 25
        end = start + 25
        options = []
        for channel in self.channels[start:end]:
            options.append(
                discord.SelectOption(label=channel.name,
                                     value=str(channel.id)))
        # If there are no channels for this page, provide a fallback option.
        if not options:
            options.append(
                discord.SelectOption(label="None",
                                     description="No channels available",
                                     value="none"))
        return options

    async def callback(self, interaction: discord.Interaction):
        selected_channel_id = self.values[0]
        if selected_channel_id == "none":
            await interaction.response.send_message("No channel selected.",
                                                    ephemeral=True)
            return

        new_value = f"<#{selected_channel_id}>"
        preferences = load_guild_preferences(interaction.guild.id)
        if self.squadron in preferences and self.notif_type in preferences[
                self.squadron]:
            preferences[self.squadron][self.notif_type] = new_value
            save_guild_preferences(interaction.guild.id, preferences)
            await interaction.response.send_message(
                f"Updated {self.notif_type} for **{self.squadron}** to {new_value}",
                ephemeral=True)
        else:
            await interaction.response.send_message("Configuration not found.",
                                                    ephemeral=True)


# Button to go to the previous page.
class PrevChannelPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Previous", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: PaginatedChannelSelectView = self.view
        if view.page > 0:
            view.page -= 1
            view.select.page = view.page
            view.select.options = view.select.get_options(view.page)
            view.select.placeholder = f"Select a channel (Page {view.page+1})"
        await interaction.response.edit_message(view=view)


# Button to go to the next page.
class NextChannelPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Next", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: PaginatedChannelSelectView = self.view
        if view.page < view.total_pages - 1:
            view.page += 1
            view.select.page = view.page
            view.select.options = view.select.get_options(view.page)
            view.select.placeholder = f"Select a channel (Page {view.page+1})"
        await interaction.response.edit_message(view=view)


# View that contains the paginated channel select and navigation buttons.
class PaginatedChannelSelectView(discord.ui.View):
    def __init__(self, guild, squadron, notif_type, page=0):
        super().__init__(timeout=180)
        self.guild = guild
        self.squadron = squadron
        self.notif_type = notif_type
        self.channels = list(guild.text_channels)
        self.page = page
        self.total_pages = math.ceil(len(self.channels) / 25)
        self.select = PaginatedChannelSelect(guild, squadron, notif_type, page)
        self.add_item(self.select)
        self.add_item(PrevChannelPageButton())
        self.add_item(NextChannelPageButton())


@bot.tree.command(name="notifications",
                  description="Manage notification settings for the server")
@app_commands.check(is_admin)
async def notifications(interaction: discord.Interaction):
    view = NotificationManagementView()
    await interaction.response.send_message(
        "Select the notification type to manage:", view=view, ephemeral=True)


@notifications.error
async def notifications_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True)


@bot.tree.command(name="donate", description="Get a link to donate to the bot, its appreciated!")
async def donate(interaction: discord.Interaction):
    donate_url = 'https://ko-fi.com/notsotoothless'
    donate_message = f"You can donate to the bot [here]({donate_url})"

    embed = discord.Embed(title="Your donation is appreciated!",
                          description=donate_message,
                          color=discord.Color.gold())
    
    embed.set_footer(text="Any amount helps!")
    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name="help", description="Get a guide on how to use the bot")
async def help(interaction: discord.Interaction):
    guide_text = (
        "**Commands Overview**\n"
        "1. **/alarm [type] [channel_id] [squadron_name]** - Set an alarm to monitor squadron changes.\n"
        "2. **/quick-log [squadron_name] [type]** - Use this in the channel you want to log in, defaults to game logs.\n"
        "3. **/find-comp [username]** - Given a username, will attempt to detail the last found SQB game.\n"
        "4. **/stat [username]** - Get the ThunderSkill stats URL for a user.\n"
        "5. **/top** - Display the top 20 squadrons and their current stats.\n"
        "6. **/time-now** - Get the current UTC time and your local time.\n"
        "7. **/set-squadron [short name]** - Store squadron name for the discord server (used for logging).\n"
        "8. **/toggle** - Enable features like Translate (more to come soon).\n"
        "9. **/sq-info [squadron] [type]** - View the details of the specified squadron, if a squadron is set (command 6), it will default to that squadron.\n"
        "10. **/track [squadron]** - View some information about a squadron.\n"
        "11. **/donate** - Get a link to donate to the bot, its appreciated!\n"
        "12. **/notifications** - Manage your alarms for the server.\n"
        "13. **/languages** - Change the default language of the bot, for now this will just change the language of the vehicles in your logs.\n"
        "14. **Translation** - Put a flag reaction under a message to translate to that language (after using /toggle).\n\n"
        "*For detailed information on each command, please read the input descriptions of each command, or reach out to not_so_toothless.*"
    )

    embed = discord.Embed(title="Bot Guide",
                          description=guide_text,
                          color=discord.Color.blue())
    embed.set_footer(text="Meow :3")
    await interaction.response.send_message(embed=embed, ephemeral=False)



if __name__ == "__main__":
    # Make sure required secrets are available
    for key in ['DISCORD_KEY', 'TEST_DISCORD_KEY', 'DEEPL_KEY', 'SID']:
        if key not in os.environ and key != 'TEST_DISCORD_KEY':
            print(f"Warning: {key} environment variable is not set")

    # Start the bot
    bot.run(TOKEN)
