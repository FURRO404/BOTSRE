# Standard Library Imports
import asyncio
import datetime as DT
import json
import logging
import os
import random
import re
import shutil
from asyncio import *
from datetime import datetime, time, timezone
import math
import deepl

# Third-Party Library Imports
import discord
from discord import Interaction, SelectOption, app_commands, ui
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from replit.object_storage import Client
from replit.object_storage.errors import ObjectNotFoundError

# Local Module Imports
import Alarms
from AutoLog import fetch_games_for_user
from Leaderboard_Parser import get_top_20, search_for_clan
from Parse_Replay import save_replay_data
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

    await cleanup_replays()
    
    snapshot_task.start()
    points_alarm_task.start()
    auto_logging_task.start()
    
    #region = "NA"
    #await execute_points_alarm_task(region)

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator
    
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


@tasks.loop(minutes=5)
async def snapshot_task():
    logging.info("Running member-leave alarm")
    for guild in bot.guilds:
        guild_id = guild.id
        guild_name = guild.name
        key = f"{guild_id}-preferences.json"

        try:
            data = client.download_as_text(key)
            preferences = json.loads(data)
        except (ObjectNotFoundError, FileNotFoundError):
            preferences = {}

        for squadron_name, squadron_preferences in preferences.items():
            channel_id = squadron_preferences.get("Leave", "").strip("<#>")
            
            old_snapshot = Alarms.load_snapshot(guild_id, squadron_name)
            new_snapshot = await Alarms.take_snapshot(squadron_name)

            if old_snapshot:
                left_members, name_changes = Alarms.compare_snapshots(old_snapshot, new_snapshot)

                if left_members:
                    if channel_id:
                        try:
                            channel_id = int(channel_id)
                            channel = bot.get_channel(channel_id)
                            if channel:
                                for member, points in left_members.items():
                                    safe_member_name = discord.utils.escape_markdown(member)
                                    if points > 0:
                                        description=f"**{safe_member_name}** left **{squadron_name}** with **{points}** points."
                                    else:
                                        description=f"**{safe_member_name}** left **{squadron_name}**."
                                    embed = discord.Embed(
                                        title="Member Left Squadron",
                                        description=description,
                                        color=discord.Color.red(),
                                    )
                                    embed.set_footer(text="This can be caused by name changes!!! Always verify.")
                                    await channel.send(embed=embed)
                            else:
                                logging.error(f"Channel ID {channel_id} not found")
                        except ValueError:
                            logging.error(f"(LEAVE) Invalid channel ID format: {channel_id} for squadron {squadron_name} in {guild_name} ({guild_id})")
                    else:
                        logging.warning(f"'Leave' not setup for squadron {squadron_name} in {guild_name} ({guild_id}).")


                if name_changes:
                    if channel_id:
                        try:
                            channel_id = int(channel_id)
                            channel = bot.get_channel(channel_id)
                            if channel:
                                for old_name, (new_name, points) in name_changes.items():
                                    old_name = discord.utils.escape_markdown(old_name)
                                    new_name = discord.utils.escape_markdown(new_name)
                                    embed = discord.Embed(
                                        title="Member Left Squadron",
                                        description=f"**{old_name}** changed their name to {new_name} in **{squadron_name}**.",
                                        color=discord.Color.dark_blue(),
                                    )
                                    embed.set_footer(text="Experimental... Might be wrong!")
                                    await channel.send(embed=embed)
                            else:
                                logging.error(f"Channel ID {channel_id} not found")
                        except ValueError:
                            logging.error(f"(NAME) Invalid channel ID format: {channel_id} for squadron {squadron_name} in {guild_name} ({guild_id})")
                    else:
                        logging.warning(f"'Leave' not setup for squadron {squadron_name} in {guild_name} ({guild_id}).")
                        
            Alarms.save_snapshot(new_snapshot, guild_id, squadron_name)


@snapshot_task.before_loop
async def before_snapshot_task():
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
        guild_name = guild.id
        key = f"{guild_id}-preferences.json"

        logging.info(f"Processing guild: {guild_id} for region: {region}")

        try:
            data = client.download_as_text(key)
            preferences = json.loads(data)
            logging.info(
                f"Successfully loaded preferences for guild: {guild_id}")
        except (ObjectNotFoundError, FileNotFoundError):
            preferences = {}

        for squadron_name, squadron_preferences in preferences.items():
            logging.info(
                f"Checking squadron: {squadron_name} for points alarm")

            squadron_info = await fetch_squadron_info(squadron_name,embed_type="points")
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
                        channel_id = int(channel_id.strip("<#>"))
                        if channel_id > 0:
                            channel = bot.get_channel(channel_id)
                            if channel:
                                logging.info(
                                    f"Sending points update to channel {channel_id} for squadron {squadron_name}"
                                )

                                changes_lines = []

                                for member, (points_change, current_points) in points_changes.items():
                                    arrow = "🌲" if points_change > 0 else "🔻"

                                    # Format with fixed widths
                                    member_str = f"{member:<20}"[:20]  # Limit name to 20 characters
                                    change_str = f"{arrow} {abs(points_change):<3}"  # Change column width of 5
                                    current_points_str = f"{current_points:>8}"  # Right-aligned 8 width
                                    changes_lines.append(f"{member_str}{change_str}  {current_points_str}")

                                # Chunk the lines into sections that fit within the max_field_length limit
                                max_field_length = 1024
                                chunks = []
                                current_chunk = "```\nName                 Change      Now\n"
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
                                    title=f"**{squadron_name} {region} Points Update**",
                                    description=f"# **Point Change:** {old_total_points} -> {sq_total_points} {chart}\n\n**Player Changes:**",
                                    color=discord.Color.blue()
                                )

                                for chunk in chunks:
                                    embed.add_field(name="\u200A", value=chunk, inline=False)

                                embed.set_footer(text="Meow :3")

                                # Send the embed
                                try:
                                    await channel.send(embed=embed)
                                    logging.info(f"Points update sent successfully for {squadron_name} in {guild_id}")
                                    
                                except Exception as e:
                                    logging.error(f"Error sending points update to {guild_id}: {e}")
                                    continue

                            else:
                                logging.error(
                                    f"Channel ID {channel_id} not found for guild {guild_id}"
                                )
                        else:
                            logging.error(
                                f"(POINTS) Invalid channel ID format: {channel_id} for squadron {squadron_name} in {guild_name} ({guild_id})"
                            )
                    else:
                        logging.info(
                            f"No new points for {squadron_name}"
                        )

                # Save the new snapshot with the region specified
                Alarms.save_snapshot(new_snapshot, guild_id, squadron_name,region)
                logging.info(f"New snapshot saved for {squadron_name} in region {region}")


@points_alarm_task.before_loop
async def before_points_alarm_task():
    await bot.wait_until_ready()


def get_shortname_from_long(longname):
    # Read the SQUADRONS.json from Replit object storage as text
    squadrons_str = client.download_as_text("SQUADRONS.json")

    # Convert the string to a dictionary
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
    key = f"{guild_id}-preferences.json"
    try:
        data = client.download_as_text(key)
        #logging.info(f"Successfully loaded preferences for guild: {guild_id}")
        return json.loads(data)
    except (ObjectNotFoundError, FileNotFoundError):
        #logging.warning(f"No preferences found for guild: {guild_id}")
        return {}

def save_guild_preferences(guild_id, preferences):
    key = f"{guild_id}-preferences.json"
    client.upload_from_text(key, json.dumps(preferences))


def load_sessions_data():
    try:
        data = client.download_as_text("SESSIONS.json")
        logging.info("Successfully loaded SESSIONS.json")
        return json.loads(data)
    except (ObjectNotFoundError, FileNotFoundError):
        logging.info("SESSIONS.json not found, creating a new one.")
        return {}

async def cleanup_replays():
    replay_file_path = "replays/"
    if os.path.exists(replay_file_path):
        shutil.rmtree(replay_file_path)
        logging.info("Deleted replay folder")


@tasks.loop(seconds=60)
async def auto_logging_task():
    try:
        now_utc = datetime.now(timezone.utc).time()

        US_START = time(0, 55)
        US_END = time(7, 20)
        EU_START = time(13, 55)
        EU_END = time(22, 20)

        if US_START <= now_utc <= US_END or EU_START <= now_utc <= EU_END:
            await auto_logging()
        else:
            logging.info("Logs not ran, not a scheduled time.")
    except Exception as e:
        logging.error(f"Unhandled exception in auto_logging: {e}")


async def auto_logging():
    try:
        logging.info("Running autologs")
        games = await fetch_games_for_user("")
        if not games:
            logging.error("No games returned from fetch_games_for_user('')")
            return
        
        squadrons_json = client.download_as_text("SQUADRONS.json")
        squadrons_data = json.loads(squadrons_json)
        sessions_data = load_sessions_data()
        scanned_sessions = set(sessions_data.get("global", []))
        
        for game in games:
            session_id = game.get("sessionIdHex")
            mission_name = game.get("missionName")
    
            if session_id in scanned_sessions:
                logging.info(f"Session {session_id} already scanned, skipping.")
                continue
            else:
                logging.info(f"Session {session_id} not scanned, downloading.")
    
            replay_file_path = f"replays/0{session_id}/replay_data.json"
    
            try:
                await save_replay_data(session_id)
                logging.info(f"Replay data saved for session {session_id}")
    
            except Exception as e:
                logging.error(f"Failed to save replay data for session {session_id}: {e}")
                scanned_sessions.add(session_id)
                continue
    
            try:
                with open(replay_file_path, "r") as replay_file:
                    replay_data = json.load(replay_file)
            except Exception as e:
                logging.error(f"Error reading replay data for session {session_id}: {e}")
                continue
            
            replay_squadrons = replay_data.get("squadrons", [])
            logging.info(f"Replay squadrons for session {session_id}: {replay_squadrons}")
            if not replay_squadrons:
                logging.warning(f"No squadrons found in replay data for session {session_id}, skipping this session.")
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
                        logging.error(f"Squadron '{squadron_short}' not found for session {session_id}.")
                        continue

            for guild in bot.guilds:
                activated = load_active_guilds(guild.id)
                if not activated:
                    logging.info(f"Guild {guild.name} ({guild.id}) is not activated for auto-logs, skipping")
                    #continue
                
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
                for squadron_name, squadron_prefs in squadrons_with_logs.items():
                    if squadron_name.lower() in long_clans:
                        if not processed:
                            logging.info(f"Processing session {session_id} for guild {guild.name} ({guild.id}) with teams {replay_squadrons}")
                            try:
                                await process_session(bot, session_id, guild.id, squadron_prefs, mission_name, guild.name)
                            except Exception as e:
                                logging.error(f"Error processing session {session_id} for guild {guild.name} ({guild.id}): {e}")
                            processed = True
                        else:
                            logging.info(f"Already processed session {session_id} for guild {guild.name} ({guild.id}), skipping duplicate.")
                        
            scanned_sessions.add(session_id)
        
        sessions_data["global"] = list(scanned_sessions)
        client.upload_from_text("SESSIONS.json", json.dumps(sessions_data, indent=4))
        logging.info("Global sessions data updated.")
    
        for session_id in scanned_sessions:
            # Construct the folder path for each session.
            folder_path = f"replays/0{session_id}"
    
            # Check if the folder exists.
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                # Iterate over all items in the folder.
                for file_name in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, file_name)
                    # Remove the file if it's a .wrpl file.
                    if os.path.isfile(file_path) and file_name.endswith(".wrpl"):
                        os.remove(file_path)
    
    except Exception as e:
        logging.error(f"Error occured in logs: {e}")


@auto_logging_task.before_loop
async def before_auto_logging_task():
    await bot.wait_until_ready()


async def process_session(bot, session_id, guild_id, squadron_preferences, map_name, guild_name):
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
    winner = replay_data.get("winning_team_squadron", "Error")
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
        embed_color = discord.Color.blue()   # No squadron set.
    elif winner == guild_squadron:
        embed_color = discord.Color.green()  # Win.
    elif loser == guild_squadron:
        embed_color = discord.Color.red()    # Loss.
    else:
        embed_color = discord.Color.purple() # Not directly involved.

    # Build the Discord embed.
    embed = discord.Embed(
        title=f"**{winner} vs {loser}**",
        description=f"**👑 • {winner}**\n{mission}\n[Replay Link]({replay_url})",
        color=embed_color,
    )

    # Add team details to the embed.
    for team in teams:
        squadron_name = team.get("squadron", "Unknown")
        players = team.get("players", [])
        player_details = "\n".join(
            f"{escape_markdown(player['nick'])} • **{player['vehicle']}**"
            for player in players
        )
        embed.add_field(name=squadron_name, value=player_details or "No players found.", inline=False)

    channel_id_str = squadron_preferences
    try:
        # Remove Discord formatting and convert to integer.
        channel_id = int(channel_id_str.strip("<#>"))
    except ValueError:
        logging.error(f"Invalid channel ID format in preferences: {channel_id_str}")
        return

    # Send the embed to the designated channel.
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
            logging.info(f"Embed sent for session {session_id} in {guild_name} ({guild_id})")

        else:
            logging.warning(f"Channel ID {channel_id} not found in {guild_name} ({guild_id})")

    except Exception as e:
        logging.error(f"Failed to send embed for session {session_id} in {guild_name} ({guild_id}): {e}")


async def update_billing(server_id, server_name, user_name, user_id, cmd_timestamp):
    try:
        raw_data = client.download_as_text("BILLING.json")
        data = json.loads(raw_data) if raw_data else {}
        logging.info("Successfully loaded BILLING.json")
    except (ObjectNotFoundError, FileNotFoundError, json.JSONDecodeError) as e:
        logging.warning(f"BILLING.json not found or invalid, creating a new one. Error: {e}")
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
    logging.info(f"Logged billing entry for {server_name} ({server_id}) - User: {user_name} ({user_id}) at {cmd_timestamp}")


@bot.tree.command(name='comp', description='Find the last known comp for a given team')
@app_commands.describe(username='The username of an enemy player')
async def find_comp(interaction: discord.Interaction, username: str):
    await interaction.response.defer()  # Defer response to handle potential long-running operations

    # Get command invocation details
    user = interaction.user
    user_name = user.name
    user_id = user.id

    guild = interaction.guild
    server_name = guild.name
    server_id = guild.id

    activated = load_active_guilds(server_id)
    if not activated:
        logging.info(f"Guild {server_name} ({server_id}) is not activated for comp, ignoring")
        
        deny_embed = discord.Embed(
            title="Server Not Activated",
            description="This server is not activated. Please contact not_so_toothless to purchase this feature.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=deny_embed)
        #return

    cmd_timestamp = DT.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    logging.info(f"FIND-COMP used by {user_name} (ID: {user_id}) in server '{server_name}' (ID: {server_id}) for username '{username}'")

    try:
        # Fetch games for the given username
        games = await fetch_games_for_user(username)
        if not games:
            await interaction.followup.send(f"No games found for user `{username}`.")
            return

        # Try processing up to 3 games deep
        for game in games[:3]:
            session_id = None
            try:
                session_id = game.get('sessionIdHex', "Error")
                mission = game.get("missionName", "Error")
                timestamp = game.get("startTime", "Error")

                if timestamp != "Error":
                    timestamp = f"<t:{timestamp}:R>"

                replay_file_path = f"replays/0{session_id}/replay_data.json"

                if not os.path.exists(replay_file_path):
                    await save_replay_data(session_id)
                    logging.info("Replay didn't exist, downloading now...")

                try:
                    with open(replay_file_path, "r") as replay_file:
                        replay_data = json.load(replay_file)
                except FileNotFoundError:
                    logging.error(f"Replay file not found for session ID {session_id}")
                    continue  # Try the next game

                # Extract relevant data from the replay JSON
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
                    description=f"**👑 • {winner}**\n{mission}\nTime: {timestamp}\n[Replay Link]({replay_url})",
                    color=discord.Color.gold(),
                )

                for team in teams:
                    squadron_name = team.get("squadron", "Unknown")
                    players = team.get("players", [])

                    player_details = "\n".join(
                        f"{escape_markdown(player['nick'])} • **{player['vehicle']}**"
                        for player in players
                    )

                    embed.add_field(name=f"{squadron_name}", value=player_details or "No players found.", inline=False)

                try:
                    await interaction.followup.send(embed=embed)

                    # Clean up replay files
                    replay_file_path = f"replays/0{session_id}"
                    if os.path.exists(replay_file_path):
                        for file_name in os.listdir(replay_file_path):
                            file_path = os.path.join(replay_file_path, file_name)
                            if os.path.isfile(file_path) and file_name.endswith(".wrpl"):
                                os.remove(file_path)

                    try:
                        await update_billing(server_id, server_name, user_name, user_id, cmd_timestamp)
                        return  # Exit after a successful match
                        
                    except Exception as e:
                        logging.error(f"Failed to bill {server_name} ({server_id}) for session {session_id}: {e}")

                except Exception as e:
                    logging.error(f"Failed to send embed for session {session_id}: {e}")
                    continue  # Try the next game

            except Exception as e:
                logging.error(f"An error occurred while processing session ID {session_id}: {e}")
                continue  # Try the next game

        # If none of the three games worked, send an error message
        await interaction.followup.send("No valid game data could be retrieved. Please try again later.")

    except Exception as e:
        logging.error(f"An error occurred in the find-comp command: {e}")
        await interaction.followup.send("An error occurred while processing the command. Please try again.")


@bot.tree.command(name="alarm", description="Set an alarm to monitor squadron changes")
@app_commands.describe(
    type="The type of alarm (e.g., Leave, Points, Logs)",
    channel_id="The ID of the channel to send alarm messages to",
    squadron_name="The SHORT name of the squadron to monitor")
@app_commands.check(is_admin)
async def alarm(interaction: discord.Interaction, type: str, channel_id: str, squadron_name: str):
    await interaction.response.defer()
    
    guild_id = interaction.guild.id
    key = f"{guild_id}-preferences.json"
    type = type.title()
    try:
        data = client.download_as_text(key)
        preferences = json.loads(data)
    except ObjectNotFoundError:
        preferences = {}

    clan_data = await search_for_clan(squadron_name.lower())
    if not clan_data:
        await interaction.followup.send("Squadron not found.", ephemeral=True)
        return

    squadron_name = clan_data.get("long_name")
    
    if squadron_name not in preferences:
        preferences[squadron_name] = {}
    
    preferences[squadron_name][type] = channel_id

    client.upload_from_text(key, json.dumps(preferences))

    await interaction.followup.send(f"Alarm of type '{type}' set for squadron '{squadron_name}' to send messages in channel ID {channel_id}.", ephemeral=True)

@alarm.error
async def alarm_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)


@bot.tree.command(name="sq-info", description="Fetch information about a squadron")
@app_commands.describe(
    squadron="The short name of the squadron to fetch information about",
    type="The type of information to display: members, points, or leave empty for full info")
async def sq_info(interaction: discord.Interaction, squadron: str = "", type: str = ""):
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
                description="No squadron specified and no squadron is set for this server.",
                color=discord.Color.red()
            )
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


active_guessing_games = {}  # Dictionary to keep track of active guessing games by channel ID


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


#@bot.tree.command(name='guessing-game', description='Start a guessing game')
async def guessing_game_command(interaction: discord.Interaction):
    logging.debug("Executing /guessing-game command")

    # Check if there's an active game in the current channel
    if interaction.channel_id in active_guessing_games:
        await interaction.response.send_message(
            "A guessing game is already in progress in this channel. Please wait for it to finish.",
            ephemeral=True)
        return

    selected_vehicle, normalized_name, image_url = guessing_game()

    if selected_vehicle is None:
        await interaction.response.send_message("No vehicles found.")
        return

    logging.debug(
        f"Selected vehicle: {selected_vehicle}, Normalized Name: {normalized_name}, Image URL: {image_url}"
    )
    embed = discord.Embed(title="Guess the Vehicle!")
    embed.set_image(url=image_url)
    embed.set_footer(text="Meow :3")
    await interaction.response.send_message(embed=embed)

    # Mark the game as active in the current channel
    active_guessing_games[interaction.channel_id] = normalized_name

    def check(m):
        return m.channel == interaction.channel and m.content.lower(
        ) == normalized_name.lower()

    timeout_seconds = 60  # Set timeout duration

    try:
        guess = await bot.wait_for('message',
                                   timeout=timeout_seconds,
                                   check=check)
        if guess:
            embed = discord.Embed(
                title="Congratulations!",
                description=
                f"Correct {guess.author.mention}! The vehicle is **{normalized_name}**",
                color=discord.Color.green())
            await interaction.followup.send(embed=embed)
            # Update the leaderboard with 1 point for a correct guess
            update_leaderboard(interaction.guild.id, guess.author.id, 1)
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="Guessing Game",
            description=
            f"Time's up! You took too long to respond. The vehicle was **{normalized_name}**",
            color=discord.Color.red())
        await interaction.followup.send(embed=embed)

    # Remove the active game from the dictionary
    del active_guessing_games[interaction.channel_id]


#@bot.tree.command(name='leaderboard', description='Show the leaderboard')
async def leaderboard_command(interaction: discord.Interaction):
    logging.debug("Executing /leaderboard command")

    guild_id = str(interaction.guild_id)
    filename = f"{guild_id}-game-rank.json"
    embed = discord.Embed(title="Top Members for this Server")

    try:
        leaderboard_json = client.download_as_text(filename)
        leaderboard = json.loads(leaderboard_json)
        sorted_leaderboard = sorted(leaderboard.items(),
                                    key=lambda x: x[1],
                                    reverse=True)

        embed.description = "\n".join([
            f"<@{user_id}>**: {score} points**"
            for user_id, score in sorted_leaderboard
        ])
        color = discord.Color.blue()
    except:
        embed.description = "No leaderboard found for this server."
        color = discord.Color.red()
    embed.set_footer(text="Meow :3")
    await interaction.response.send_message(embed=embed)


def choose_vehicles_from_both_files():
    air_file_path = "DATA/Air.txt"
    ground_file_path = "DATA/Ground.txt"

    air_vehicles = choose_random_vehicle(air_file_path)
    ground_vehicles = choose_random_vehicle(ground_file_path)

    all_vehicles = air_vehicles + ground_vehicles
    if len(all_vehicles) < 10:
        return all_vehicles  # Return all if less than 10
    return random.sample(all_vehicles, 10)


def modify_vehicles(vehicles, count):
    fake_vehicles = random.sample(vehicles, count)
    modified_vehicles = vehicles.copy()

    true_fakes = []
    for vehicle in fake_vehicles:
        vehicle_name, normalized_name, br = vehicle
        logging.debug(f"Original vehicle name: {vehicle_name}")

        # Modify the name (change a number)
        if any(char.isdigit() for char in vehicle_name):
            modified_name = ''.join([
                str((int(char) + 1) % 10) if char.isdigit() else char
                for char in vehicle_name
            ])
        else:
            choices = [" Mk II", "-C"]
            modified_name = vehicle_name + random.choice(choices)

        normalized_modified_name = normalize_name(modified_name)
        logging.debug(
            f"Modified vehicle name: {modified_name}, Normalized modified name: {normalized_modified_name}"
        )

        true_fakes.append((modified_name, normalized_modified_name, br))
        modified_vehicles.remove(vehicle)
        modified_vehicles.append((modified_name, normalized_modified_name, br))

    return modified_vehicles, true_fakes


class TriviaDropdown(ui.Select):

    def __init__(self, vehicles, fake_vehicles, fake_count, difficulty,
                 interaction):
        options = [
            SelectOption(label=normalize_name(vehicle[0]),
                         value=normalize_name(vehicle[0]))
            for vehicle in vehicles
        ]
        random.shuffle(options)  # Shuffle the options to randomize their order
        super().__init__(placeholder="Select the fake vehicles...",
                         max_values=fake_count,
                         options=options)
        self.fake_count = fake_count
        self.fake_vehicles = fake_vehicles
        self.difficulty = difficulty
        self.interaction_user = interaction.user

    async def callback(self, interaction: Interaction):
        if interaction.user != self.interaction_user:
            await interaction.response.send_message(
                "Only the user who started the game can play.", ephemeral=True)
            return

        chosen_fakes = self.values
        true_fakes = [
            normalize_name(vehicle[0]) for vehicle in self.fake_vehicles
        ]
        logging.debug(f"Chosen fakes: {chosen_fakes}")
        logging.debug(f"True fakes: {true_fakes}")

        # Sort the lists before comparison
        chosen_fakes_sorted = sorted(chosen_fakes)
        true_fakes_sorted = sorted(true_fakes)
        correct_count = sum(
            [1 for fake in chosen_fakes_sorted if fake in true_fakes_sorted])

        if correct_count == self.fake_count and correct_count == len(
                chosen_fakes):
            points = {"easy": 1, "medium": 2, "hard": 3}[self.difficulty]
            update_leaderboard(interaction.guild.id, interaction.user.id,
                               points)
            embed = discord.Embed(
                title="Congratulations!",
                description=
                f"Correct {interaction.user.mention}! You found all the fake vehicles.",
                color=discord.Color.green())
            embed.set_footer(text="Meow :3")
            await interaction.response.send_message(embed=embed)
        else:
            remaining_fakes = self.fake_count - correct_count
            embed = discord.Embed(
                title="Try Again!",
                description=
                f"You have {remaining_fakes} fake vehicles left. Try again!",
                color=discord.Color.red())
            await interaction.response.send_message(embed=embed)


class TriviaView(ui.View):

    def __init__(self, vehicles, fake_vehicles, fake_count, difficulty,
                 interaction):
        super().__init__()
        self.add_item(
            TriviaDropdown(vehicles, fake_vehicles, fake_count, difficulty,
                           interaction))
        self.fake_vehicles = fake_vehicles


#@bot.tree.command(name="trivia", description="Play a War Thunder vehicle trivia game")
#@app_commands.describe(difficulty="Choose the difficulty level: easy, medium, or hard")
async def trivia(interaction: Interaction, difficulty: str = "medium"):
    user_id = interaction.user.id
    difficulty = difficulty.lower()  # Normalize difficulty to lowercase
    difficulty_levels = {"easy": 1, "medium": 2, "hard": 3}

    if difficulty not in difficulty_levels:
        await interaction.response.send_message(
            "Invalid difficulty level. Please choose from: easy, medium, or hard.",
            ephemeral=True)
        return

    fake_count = difficulty_levels[difficulty]

    vehicles = choose_vehicles_from_both_files()

    if len(vehicles) < 10:
        await interaction.response.send_message(
            "Not enough vehicles in the files to start the trivia.")
        return

    modified_vehicles, fake_vehicles = modify_vehicles(vehicles, fake_count)

    view = TriviaView(modified_vehicles, fake_vehicles, fake_count, difficulty,
                      interaction)
    view.message = await interaction.response.send_message(
        "Select the fake vehicles from the dropdown below:", view=view)


@bot.tree.command(name='time-now',
                  description='Get the current UTC and local time')
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


#@bot.tree.command(name="randomizer", description="Choose a random vehicle and its BR.")
async def randomizer(interaction: discord.Interaction):
    # Run the randomizer_game function to get the vehicle details
    result = randomizer_game()

    # Create a Discord embed to display the result nicely
    embed = discord.Embed(
        title="Random Vehicle",
        description=result,
        color=discord.Color.purple()  # You can change the color as needed
    )

    # Send the embed as the response
    embed.set_footer(text="Meow :3")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='set-squadron', description='Set the squadron tag for this server')
@app_commands.describe(abbreviated_name='The short name of the squadron to set')
async def set_squadron(interaction: discord.Interaction, abbreviated_name: str):
    try:
        # Defer the response to prevent timeouts
        await interaction.response.defer()

        # File to store squadron data
        filename = "SQUADRONS.json"

        # Download existing squadron data
        try:
            squadrons_json = client.download_as_text(filename)
            squadrons = json.loads(squadrons_json)
        except Exception:
            logging.warning("SQUADRONS.json not found. Creating a new one."
                            )  # Nigh Impossible
            squadrons = {}

        # Ensure the server doesn't already have a different squadron set
        guild_id = str(interaction.guild_id)
        if guild_id in squadrons and squadrons[guild_id][
                'SQ_ShortHand_Name'] != re.sub(r'\W+', '', abbreviated_name):
            embed = discord.Embed(
                title="Error",
                description=
                f"This server already has a different squadron set: {squadrons[guild_id]['SQ_LongHandName']}.",
                color=discord.Color.red())
            embed.set_footer(text="Meow :3")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Sanitize and store the short-hand and long-hand names
        sq_short_hand_name = re.sub(r'\W+', '', abbreviated_name)
        clan_data = await search_for_clan(sq_short_hand_name.lower())
        sq_long_hand_name = clan_data.get("long_name")

        # Update squadron data for the current Discord server
        squadrons[guild_id] = {
            "SQ_ShortHand_Name": sq_short_hand_name,
            "SQ_LongHandName": sq_long_hand_name
        }

        # Upload the updated squadron data
        client.upload_from_text(filename, json.dumps(squadrons))

        # Create the embed for a successful response
        embed = discord.Embed(
            title="Squadron Set",
            description=
            f"Squadron **{sq_long_hand_name}** has been set for this server.",
            color=discord.Color.green())
        embed.add_field(name="Short Name",
                        value=sq_short_hand_name,
                        inline=True)
        embed.add_field(name="Long Name", value=sq_long_hand_name, inline=True)
        embed.set_footer(text="Meow :3")

        await interaction.followup.send(embed=embed, ephemeral=False)

    except Exception as e:
        logging.error(f"Error setting squadron: {e}")
        embed = discord.Embed(
            title="Error",
            description=f"An error occurred while setting the squadron: {e}",
            color=discord.Color.red())
        await interaction.followup.send(embed=embed, ephemeral=True)


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
                f"**Playtime:** {formatted_playtime}\n"
                "\u200b"  # Adds spacing
            ),
            inline=True  # Each squadron appears on a new line
        )

    embed.set_footer(text="Meow :3")
    await interaction.followup.send(embed=embed, ephemeral=False)


async def load_features(guild_id):
    key = f"{guild_id}-features.json"

    try:
        data = client.download_as_text(key)
        return json.loads(data)
    except (ObjectNotFoundError, FileNotFoundError):
        # If file doesn't exist, create it with default values
        features = {"Translate": "False"}
        client.upload_from_text(key, json.dumps(features))
        return features

async def save_features(guild_id, features):
    key = f"{guild_id}-features.json"
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
        
# Dictionary mapping flag emojis to language codes
LANGUAGE_MAP = {
    "🇷🇺": "ru",    # Russian
    "🇺🇸": "en-us",  # English (US)
    "🇬🇧": "en-gb",  # English (UK)
    "🇪🇸": "es",    # Spanish
    "🇫🇷": "fr",    # French
    "🇩🇪": "de",    # German
    "🇨🇳": "zh-cn",  # Chinese (Simplified)
    "🇯🇵": "ja",    # Japanese
    "🇰🇷": "ko",    # Korean
    "🇮🇹": "it",    # Italian
    "🇵🇹": "pt-PT",    # Portuguese
    "🇵🇱": "pl",    # Polish
    "🇱🇹": "lt",    # Lithuanian
    "🇱🇻": "lv",    # Latvian
    "🇪🇪": "et",    # Estonian
    "🇺🇦": "uk",    # Ukrainian
    "🇲🇰": "mk",    # Macedonian
    "🇨🇿": "cs",    # Czech
    "🇷🇴": "ro",    # Romanian
    "🇧🇬": "bg",    # Bulgarian
    "🇬🇷": "el",    # Greek
    "🇭🇺": "hu",    # Hungarian
    "🏳️‍🌈": "pl"
}


DEEPL_API_KEY = os.environ.get("DEEPL_KEY")
translator = deepl.Translator(DEEPL_API_KEY)

translated_messages = set()

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

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    message = reaction.message  
    # Ignore reactions on messages from bots
    if message.author.bot:
        return

    # Check if this message has already been translated
    if message.id in translated_messages:
        return

    # Sanitize the message content before translation
    text = sanitize_text(message.content, message)
    flag = reaction.emoji
    guild_id = message.guild.id

    if flag not in LANGUAGE_MAP:
        return  

    features = await load_features(guild_id)
    if not features or features.get("Translate") != "True":
        embed = discord.Embed(
            title="Translation Disabled",
            description="Translations are not enabled for this server.\nUse /toggle 'Translate' to enable.",
            color=discord.Color.red()
        )
        logging.info("Translation disabled!")
        return

    target_language = LANGUAGE_MAP[flag]

    try:
        await reaction.message.remove_reaction(flag, user)
    except discord.Forbidden:
        pass  # Bot lacks permissions to remove reactions

    translated_text = perform_translation(text, target_language)

    if not translated_text:
        await message.channel.send(f"Translation failed for: {flag}", delete_after=5)
        return

    username = escape_markdown(message.author.display_name)
    sent_message = await message.channel.send(f"**{username} - ({target_language.upper()}):** {translated_text}")
    await sent_message.delete(delay=60)

    # Add message ID to the translated list and schedule its removal after 60 seconds
    translated_messages.add(message.id)
    async def remove_translated_id():
        await asyncio.sleep(70)
        translated_messages.discard(message.id)
    asyncio.create_task(remove_translated_id())


async def return_latest_battle(sq_long_name):
    sessions, guild_id = {}, ""
    squadron_info = await fetch_squadron_info(sq_long_name, embed_type="logs")
    found_sessions, maps, time_stamps = await extract_sessions_from_squadron(squadron_info, sessions, guild_id)

    if not time_stamps:
        return "No recorded battles found."

    latest_timestamp = max(time_stamps)
    return f"<t:{latest_timestamp}:R>"
    

@bot.tree.command(name="track", description="Track a certain squadron to see when they last played SQB")
@app_commands.describe(squadron_short_name="Short name of the squadron to track")
async def track_squadron(interaction: discord.Interaction, squadron_short_name: str):
    await interaction.response.defer()
    logging.info("Running /track")

    clan_data = await search_for_clan(squadron_short_name.lower())
    if not clan_data:
        await interaction.followup.send("Squadron not found.", ephemeral=True)
        return

    #clan_name_long = clan_data.get("long_name")
    clan_tag = clan_data.get("tag")
    points = int(clan_data.get("clanrating"))
    ground_kills = int(clan_data.get("g_kills"))
    air_kills = int(clan_data.get("a_kills"))
    deaths = int(clan_data.get("deaths"))
    battles = int(clan_data.get("battles"))
    wins = int(clan_data.get("wins"))
    members = clan_data.get("members")
    #latest_stamp = await return_latest_battle(clan_name_long)

    total_kills = ground_kills + air_kills
    kd_ratio = total_kills / deaths if deaths > 0 else total_kills

    win_rate = (wins / battles) * 100 if battles > 0 else 0
    win_rate_percentage = f"{win_rate:.2f}%"

    embed = discord.Embed(
        title=f"**{clan_tag}**",
        color=discord.Color.green()
    )
    
    embed.add_field(name="Points", value=points, inline=True)
    embed.add_field(name="Wins", value=wins, inline=True)
    embed.add_field(name="Win Rate", value=win_rate_percentage, inline=True)
    embed.add_field(name="Members", value=members, inline=True)
    embed.add_field(name="KD Ratio", value=f"{kd_ratio:.2f}", inline=True)
    embed.set_footer(text="Meow :3")
    await interaction.followup.send(embed=embed, ephemeral=False)


class NotificationTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Logs", description="Manage Logs notifications"),
            discord.SelectOption(label="Points", description="Manage Points notifications"),
            discord.SelectOption(label="Leave", description="Manage Leave notifications")
        ]
        super().__init__(placeholder="Select notification type", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        notif_type = self.values[0]
        # Proceed to Step 2: Squadron selection.
        view = create_squadron_select_view(interaction.guild.id, notif_type)
        await interaction.response.send_message(
            f"Selected **{notif_type}**. Now choose the squadron to manage:",
            view=view,
            ephemeral=True
        )

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
                state = "Disabled" if channel_val.startswith("<#DISABLED-") else "Enabled"
                options.append(discord.SelectOption(label=squadron, description=f"{state}: {channel_val}"))
        if not options:
            options.append(discord.SelectOption(label="None", description="No squadrons configured", value="none"))
        super().__init__(placeholder="Select a squadron", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_squadron = self.values[0]
        if selected_squadron == "none":
            await interaction.response.send_message("No squadron available for this notification type.", ephemeral=True)
            return

        # Retrieve the current channel value for the selected notification type.
        preferences = load_guild_preferences(self.guild_id)
        squadron_settings = preferences.get(selected_squadron, {})
        channel_value = squadron_settings.get(self.notif_type, "Not configured")
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
            ephemeral=True
        )

# New classes for paginated squadron selection (> 25 squadrons, somehow.)
class PaginatedSquadronSelect(discord.ui.Select):
    def __init__(self, guild_id, notif_type, squadron_list, page=0):
        self.guild_id = guild_id
        self.notif_type = notif_type
        self.squadron_list = squadron_list  # List of tuples: (squadron, settings)
        self.page = page
        options = self.get_options(page)
        super().__init__(placeholder=f"Select a squadron (Page {page+1})", min_values=1, max_values=1, options=options)

    def get_options(self, page):
        start = page * 25
        end = start + 25
        options = []
        for squadron, settings in self.squadron_list[start:end]:
            channel_val = settings[self.notif_type]
            state = "Disabled" if channel_val.startswith("<#DISABLED-") else "Enabled"
            options.append(discord.SelectOption(label=squadron, description=f"{state}: {channel_val}"))
        if not options:
            options.append(discord.SelectOption(label="None", description="No squadrons configured", value="none"))
        return options

    async def callback(self, interaction: discord.Interaction):
        selected_squadron = self.values[0]
        if selected_squadron == "none":
            await interaction.response.send_message("No squadron available for this notification type.", ephemeral=True)
            return

        preferences = load_guild_preferences(self.guild_id)
        squadron_settings = preferences.get(selected_squadron, {})
        channel_value = squadron_settings.get(self.notif_type, "Not configured")
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
            ephemeral=True
        )

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
        self.select = PaginatedSquadronSelect(guild_id, notif_type, squadron_list, page)
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
        label = "Enable" if channel_value.startswith("<#DISABLED-") else "Disable"
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.guild_id = guild_id
        self.notif_type = notif_type
        self.squadron = squadron

    async def callback(self, interaction: discord.Interaction):
        preferences = load_guild_preferences(self.guild_id)
        squadron_settings = preferences.get(self.squadron, {})
        current_value = squadron_settings.get(self.notif_type)
        if not current_value:
            await interaction.response.send_message("Configuration not found.", ephemeral=True)
            return

        # Toggle by adding or removing "DISABLED-"
        if current_value.startswith("<#DISABLED-"):
            new_value = "<#" + current_value[len("<#DISABLED-"):]
        else:
            new_value = current_value.replace("<#", "<#DISABLED-", 1)
        preferences[self.squadron][self.notif_type] = new_value
        save_guild_preferences(self.guild_id, preferences)

        self.label = "Enable" if new_value.startswith("<#DISABLED-") else "Disable"
        await interaction.response.send_message(
            f"{self.notif_type} for **{self.squadron}** is now " +
            ("disabled." if new_value.startswith("<#DISABLED-") else "enabled."),
            ephemeral=True
        )
        await interaction.edit_original_response(view=self.view)

class ChangeChannelButton(discord.ui.Button):
    def __init__(self, guild_id, notif_type, squadron):
        super().__init__(label="Change Channel", style=discord.ButtonStyle.secondary)
        self.guild_id = guild_id
        self.notif_type = notif_type
        self.squadron = squadron

    async def callback(self, interaction: discord.Interaction):
        view = ChannelSelectView(interaction.guild, self.notif_type, self.squadron)
        await interaction.response.send_message("Select a new channel:", view=view, ephemeral=True)

class ChannelSelect(discord.ui.Select):
    def __init__(self, guild, notif_type, squadron):
        self.notif_type = notif_type
        self.squadron = squadron
        options = []
        for channel in guild.text_channels:
            options.append(discord.SelectOption(label=channel.name, value=str(channel.id)))
        super().__init__(placeholder="Select a channel", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_channel_id = self.values[0]
        new_value = f"<#{selected_channel_id}>"
        preferences = load_guild_preferences(interaction.guild.id)
        if self.squadron in preferences and self.notif_type in preferences[self.squadron]:
            preferences[self.squadron][self.notif_type] = new_value
            save_guild_preferences(interaction.guild.id, preferences)
            await interaction.response.send_message(
                f"Updated {self.notif_type} for **{self.squadron}** to {new_value}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("Configuration not found.", ephemeral=True)

class ChannelSelectView(discord.ui.View):
    def __init__(self, guild, notif_type, squadron):
        super().__init__(timeout=180)
        self.add_item(ChannelSelect(guild, notif_type, squadron))

class ToggleView(discord.ui.View):
    def __init__(self, guild_id, notif_type, squadron):
        super().__init__(timeout=180)
        preferences = load_guild_preferences(guild_id)
        channel_value = preferences.get(squadron, {}).get(notif_type, "Not configured")
        self.add_item(ToggleButton(guild_id, notif_type, squadron, channel_value))
        self.add_item(ChangeChannelButton(guild_id, notif_type, squadron))


@bot.tree.command(name="notifications", description="Manage notification settings for the server")
@app_commands.check(is_admin)
async def notifications(interaction: discord.Interaction):
    view = NotificationManagementView()
    await interaction.response.send_message(
        "Select the notification type to manage:",
        view=view,
        ephemeral=True
    )

@notifications.error
async def notifications_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)


@bot.tree.command(name="help", description="Get a guide on how to use the bot")
async def help(interaction: discord.Interaction):
    guide_text = (
        "**Commands Overview**\n"
        "1. **/alarm [type] [channel_id] [squadron_name]** - Set an alarm to monitor squadron changes.\n"
        "2. **/comp [username]** - Given a username, will attempt to detail the last found SQB game.\n"
        "3. **/stat [username]** - Get the ThunderSkill stats URL for a user.\n"
        "4. **/top** - Display the top 20 squadrons and their current stats.\n"
        "5. **/time-now** - Get the current UTC time and your local time.\n"
        "6. **/set-squadron [short name]** - Store squadron name for the discord server (used for logging).\n"
        "7. **/toggle** - Enable features like Translate (more to come soon).\n"
        "8. **/sq-info [squadron] [type]** - View the details of the specified squadron, if a squadron is set (command 6), it will default to that squadron.\n"
        "9. **/track [squadron]** - View the last time a squadron played.\n"
        "10. **/help** - Get a guide on how to use the bot.\n"
        "11. **/notifications** - Manage your alarms for the server.\n"
        "12. **Translation** - Put a flag reaction under a message to translate to that language (after using /enable).\n\n"
        "*For detailed information on each command, please read the input descriptions of each command, or reach out to not_so_toothless.*"
    )

    embed = discord.Embed(title="Bot Guide",
                          description=guide_text,
                          color=discord.Color.blue())
    embed.set_footer(text="Meow :3")
    await interaction.response.send_message(embed=embed, ephemeral=False)

bot.run(TOKEN)