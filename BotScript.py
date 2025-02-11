# Standard Library Imports
import os
import json
import logging
import asyncio
from asyncio import *
import random
import datetime as DT
from datetime import datetime, time, timezone
import time as T
import re
import shutil

# Third-Party Library Imports
import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from discord import app_commands, ui, Interaction, SelectOption
from replit.object_storage import Client
from replit.object_storage.errors import ObjectNotFoundError
from googletrans import Translator

# Local Module Imports
import Alarms
from SQ_Info import fetch_squadron_info
from AutoLog import fetch_games_for_user
from SQ_Info_Auto import process_all_squadrons
from Parse_Replay import save_replay_data

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)

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
    snapshot_task.start()
    points_alarm_task.start()
    logs_snapshot_task.start()
    
    #region = "US"
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


@tasks.loop(minutes=10)
async def snapshot_task():
    logging.info("Running member-leave alarm")
    for guild in bot.guilds:
        guild_id = guild.id
        key = f"{guild_id}-preferences.json"

        try:
            data = client.download_as_text(key)
            preferences = json.loads(data)
        except (ObjectNotFoundError, FileNotFoundError):
            preferences = {}

        for squadron_name, squadron_preferences in preferences.items():
            old_snapshot = Alarms.load_snapshot(guild_id, squadron_name)
            new_snapshot = await Alarms.take_snapshot(squadron_name)

            if old_snapshot:
                left_members = Alarms.compare_snapshots(
                    old_snapshot, new_snapshot)

                # Skip this iteration if there are no left members
                if left_members == "EMPTY":
                    logging.info(
                        f"No new members were found for {squadron_name}, skipping"
                    )
                    continue

                if left_members:
                    channel_id = squadron_preferences.get("Leave", "").strip("<#>")

                    if channel_id:
                        try:
                            channel_id = int(channel_id)
                            channel = bot.get_channel(channel_id)
                            if channel:
                                for member, points in left_members.items():
                                    safe_member_name = discord.utils.escape_markdown(member)
                                    embed = discord.Embed(
                                        title="Member Left Squadron",
                                        description=f"**{safe_member_name}** left **{squadron_name}** with **{points}** points.",
                                        color=discord.Color.red(),
                                    )
                                    #embed.set_footer(text=f"This can be caused by name changes!!! Always verify.")
                                    await channel.send(embed=embed)
                            else:
                                logging.error(f"Channel ID {channel_id} not found")
                        except ValueError:
                            logging.error(f"Invalid channel ID format: {channel_id} for squadron {squadron_name}")
                    else:
                        logging.error(f"'Leave' channel ID is missing or empty for squadron {squadron_name}.")

            Alarms.save_snapshot(new_snapshot, guild_id, squadron_name)


@snapshot_task.before_loop
async def before_snapshot_task():
    await bot.wait_until_ready()


@tasks.loop(minutes=1)
async def points_alarm_task():
    now_utc = datetime.now(timezone.utc).time()

    # Define the region based on the current time
    if now_utc.hour == 22 and now_utc.minute == 15:
        region = "EU"
        await execute_points_alarm_task(region)
    elif now_utc.hour == 7 and now_utc.minute == 15:
        region = "US"
        await execute_points_alarm_task(region)


async def execute_points_alarm_task(region):
    logging.info("Running points-update alarm")
    for guild in bot.guilds:
        guild_id = guild.id
        key = f"{guild_id}-preferences.json"

        logging.info(f"Processing guild: {guild_id} for region: {region}")

        try:
            data = client.download_as_text(key)
            preferences = json.loads(data)
            logging.info(
                f"Successfully loaded preferences for guild: {guild_id}")
        except (ObjectNotFoundError, FileNotFoundError):
            preferences = {}
            logging.warning(f"No preferences found for guild: {guild_id}")

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
                    logging.info(
                        f"Loaded old snapshot for {squadron_name}, region {region}"
                    )
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
                                MAX_NAME_LENGTH = 20

                                for member, (points_change, current_points) in points_changes.items():
                                    arrow = "🌲" if points_change > 0 else "🔻"

                                    # Format with fixed widths
                                    member_str = f"{member:<20}"[:20]  # Limit name to 20 characters
                                    change_str = f"{arrow} {abs(points_change):<3}"  # Change column width of 5
                                    current_points_str = f"{current_points:>8}"  # Right-aligned 8 width
                                    changes_lines.append(f"{member_str}{change_str}{current_points_str}")

                                # Chunk the lines into sections that fit within the max_field_length limit
                                max_field_length = 1024
                                chunks = []
                                current_chunk = "```\nName                Change   Now\n"
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
                                await channel.send(embed=embed)
                                logging.info(f"Points update sent successfully for {squadron_name} in {guild_id}")

                            else:
                                logging.error(
                                    f"Channel ID {channel_id} not found for guild {guild_id}"
                                )
                        else:
                            logging.error(
                                f"Invalid channel ID format: {channel_id} for squadron {squadron_name}"
                            )
                    else:
                        logging.info(
                            f"No channel set for 'Points' type Alarms for squadron {squadron_name}"
                        )

                # Save the new snapshot with the region specified
                Alarms.save_snapshot(new_snapshot, guild_id, squadron_name,region)
                logging.info(
                    f"New snapshot saved for {squadron_name} in region {region}"
                )


@points_alarm_task.before_loop
async def before_points_alarm_task():
    await bot.wait_until_ready()


def get_shortname_from_long(longname):
    # Read the SQUADRONS.json from Replit object storage as text
    squadrons_str = client.download_as_text("SQUADRONS.json")

    # Convert the string to a dictionary
    squadrons = json.loads(squadrons_str)

    # Iterate through the dictionary to find the matching long name
    for server_id, squadron_info in squadrons.items():
        if squadron_info["SQ_LongHandName"] == longname:
            return squadron_info["SQ_ShortHand_Name"]

    return None


@tasks.loop(minutes=5)
async def logs_snapshot_task():
    now_utc = datetime.now(timezone.utc).time()
    # Run logs_snapshot only while US/EU timeslot are open
    if (time(13, 55) <= now_utc <= time(22, 10)) or (time(12, 55) <= now_utc <= time(7, 10)):
        await logs_snapshot()
    else:
        #await logs_snapshot()
        logging.info("Logs not ran, not a scheduled time.")


async def logs_snapshot():
    logging.info("Running log-snapshot task")

    for guild in bot.guilds:
        guild_id = guild.id
        logging.info(f"Processing guild: {guild_id}")

        preferences = load_guild_preferences(guild_id)
        #squadrons = load_squadrons_data()
        sessions_data = load_sessions_data()

        if str(guild_id) not in sessions_data:
            sessions_data[str(guild_id)] = []
            logging.info(f"Added new guild entry for guild: {guild_id} in sessions.json")

        all_found_sessions = await process_guild_squadrons(guild_id, preferences, sessions_data)
        update_sessions_data(guild_id, all_found_sessions, sessions_data)


def load_guild_preferences(guild_id):
    key = f"{guild_id}-preferences.json"
    try:
        data = client.download_as_text(key)
        logging.info(f"Successfully loaded preferences for guild: {guild_id}")
        return json.loads(data)
    except (ObjectNotFoundError, FileNotFoundError):
        logging.warning(f"No preferences found for guild: {guild_id}")
        return {}


def load_squadrons_data():
    try:
        data = client.download_as_text("SQUADRONS.json")
        logging.info("Loaded SQUADRONS.json")
        return json.loads(data)
    except (ObjectNotFoundError, FileNotFoundError):
        logging.error("SQUADRONS.json not found or could not be loaded")
        return {}


def load_sessions_data():
    try:
        data = client.download_as_text("SESSIONS.json")
        logging.info("Successfully loaded SESSIONS.json")
        return json.loads(data)
    except (ObjectNotFoundError, FileNotFoundError):
        logging.info("SESSIONS.json not found, creating a new one.")
        return {}


async def process_guild_squadrons(guild_id, preferences, sessions):
    all_found_sessions = []
    valid_sessions = []
    # Extract only squadrons that have "Logs" defined
    squadrons_with_logs = {
        squadron: prefs["Logs"]
        for squadron, prefs in preferences.items()
        if "Logs" in prefs
    }
    logging.info(squadrons_with_logs)
    
    for squadron_name, log_channel in squadrons_with_logs.items():
        logging.info(f"Logs are enabled for squadron: {squadron_name} in guild: {guild_id} (Logs Channel: {log_channel})")

        squadron_info = await fetch_squadron_info(squadron_name, embed_type="logs")
        found_sessions = await extract_sessions_from_squadron(squadron_info, sessions, guild_id)

        valid_sessions = filter_valid_sessions(found_sessions)
        logging.info(f"Valid session IDs (found 2 or more times): {valid_sessions}")

        try:
            for session_id in valid_sessions:
                await process_session(bot, session_id, guild_id, preferences[squadron_name])

            all_found_sessions.extend(found_sessions)
        except Exception as e:
            logging.error(f"Error processing sessions for squadron {squadron_name} in guild {guild_id}: {e}", exc_info=True)
            
    return all_found_sessions


async def extract_sessions_from_squadron(squadron_info, sessions, guild_id):
    found_sessions = []

    if not squadron_info:
        return found_sessions

    # Extract usernames
    usernames = [
        username
        for field in squadron_info.fields
        for username in field.value.split("\n")
    ]

    # Use asyncio.gather to fetch game data concurrently
    user_game_tasks = [fetch_games_for_user(username) for username in usernames]
    user_games_results = await asyncio.gather(*user_game_tasks, return_exceptions=True)

    for games in user_games_results:
        if isinstance(games, Exception):
            logging.warning(f"Error fetching games: {games}")
            continue

        for game in games:
            session_id = game.get("sessionIdHex")
            if session_id and session_id not in sessions[str(guild_id)]:
                found_sessions.append(session_id)

    return found_sessions


def filter_valid_sessions(found_sessions):
    session_counts = {}
    for session in found_sessions:
        session_counts[session] = session_counts.get(session, 0) + 1
        
    valid_sessions = [session for session, count in session_counts.items() if count >= 2]
    return valid_sessions


def update_sessions_data(guild_id, all_found_sessions, sessions):
    if all_found_sessions:
        existing_sessions = sessions.get(str(guild_id), [])
        updated_sessions = list(set(existing_sessions + all_found_sessions))
        sessions[str(guild_id)] = updated_sessions

        client.upload_from_text("SESSIONS.json", json.dumps(sessions, indent=4))
        logging.info(f"Updated SESSIONS.json for guild {guild_id} with new sessions: {all_found_sessions}")


@logs_snapshot_task.before_loop
async def before_logs_snapshot_task():
    await bot.wait_until_ready()


async def process_session(bot, session_id, guild_id, squadron_preferences):
    """Processes a single session, saves replay data, and sends embeds to the specified Discord channel."""
    try:
        await save_replay_data(session_id)
    except Exception as e:
        logging.error(f"Failed to save replay data for session {session_id}: {e}")
        return  # Skip this session but continue with others

    replay_file_path = f"replays/0{session_id}/replay_data.json"
    try:
        with open(replay_file_path, "r") as replay_file:
            replay_data = json.load(replay_file)
    except FileNotFoundError:
        logging.error(f"Replay file not found for session ID {session_id}")
        return
    except json.JSONDecodeError:
        logging.error(f"Replay file for session ID {session_id} is invalid JSON")
        return

    winner = replay_data.get("winning_team_squadron", None)

    # Skip if winner is None (null in JSON)
    if winner is None:
        logging.warning(f"Session {session_id} as 'winning_team_squadron' is null.")
        #return

    squadrons = replay_data.get("squadrons", [])
    weather = replay_data.get("weather", "Unknown")
    mission = replay_data.get("mission", "In Progress")
    time_of_day = replay_data.get("time_of_day", "Unknown")
    teams = replay_data.get("teams", [])

    try:
        squadrons_json = client.download_as_text("SQUADRONS.json")
        squadrons_data = json.loads(squadrons_json)
    except Exception:
        logging.warning("SQUADRONS.json not found. Creating a new one.")
        squadrons_data = {}

    # Get the expected squadron shortname for this guild
    guild_data = squadrons_data.get(str(guild_id), {})
    guild_squadron = guild_data.get("SQ_ShortHand_Name", None) #EXLY

    # Determine the losing squadron
    if len(squadrons) >= 2:
        loser = squadrons[0] if squadrons[1] == winner else squadrons[1]
    else:
        loser = None  # Fallback in case of unexpected data

    if guild_squadron is None:
        embed_color = discord.Color.blue()  # No squadron set 🟦
        color_name = "blue"
    elif winner == guild_squadron:
        embed_color = discord.Color.green()  # Win 🟩
        color_name = "green"
    elif loser == guild_squadron:
        embed_color = discord.Color.red()  # Loss 🟥
        color_name = "red"
    else:
        embed_color = discord.Color.purple()  # Not involved, but squadron is set 🟪
        color_name = "purple"
    
    embed = discord.Embed(
        title=f"**{winner} vs {loser}**",
        description=f"**👑 • {winner}**\nMap: {mission}\nGame ID: {session_id}",
        color=embed_color,
    )

    for team in teams:
        squadron_name = team.get("squadron", "Unknown")
        players = team.get("players", [])

        player_details = "\n".join(
            f"{escape_markdown(player['nick'])} • **{player['vehicle']}**"
            for player in players
        )

        embed.add_field(name=f"{squadron_name}", value=player_details or "No players found.", inline=False)

    channel_id = squadron_preferences.get("Logs", "")
    channel_id = int(channel_id.strip("<#>"))
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
            logging.info(f"Embed sent for session {session_id} in guild {guild_id} with color {color_name}")

            replay_file_path = f"replays/0{session_id}"
            if os.path.exists(replay_file_path):
                shutil.rmtree(replay_file_path)
                logging.info(f"Deleted replay folder: {replay_file_path}")

        else:
            logging.warning(f"Channel ID {channel_id} not found in guild {guild_id}")

    except Exception as e:
        logging.error(f"Failed to send embed for session {session_id}: {e}")


@bot.tree.command(name='comp', description='Find the last known comp for a given team')
@app_commands.describe(username='The username of an enemy player')
async def find_comp(interaction: discord.Interaction, username: str):
    await interaction.response.defer()  # Defer response to handle potential long-running operations

    # Get command invocation details
    user = interaction.user
    server = interaction.guild
    timestamp = DT.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')    
    
    try:
        # Fetch games for the given username
        games = await fetch_games_for_user(username)
        if not games:
            await interaction.followup.send(f"No games found for user `{username}`.")
            return

        game = games[0]
        session_id = game.get('sessionIdHex')
        if not session_id:
            await interaction.followup.send(f"Could not retrieve session ID for user `{username}`.")
            return

        timestamp = game.get("startTime", "ERR")
        if timestamp != "ERR":
            timestamp = f"<t:{timestamp}:R>"
        
        # Save replay data for the session
        await save_replay_data(session_id)

        # Load the replay data saved for the session
        replay_file_path = f"replays/0{session_id}/replay_data.json"
        try:
            with open(replay_file_path, "r") as replay_file:
                replay_data = json.load(replay_file)
        except FileNotFoundError:
            logging.error(f"Replay file not found for session ID {session_id}")
            await interaction.followup.send(f"Replay data not found for session `{session_id}`.")
            return
        
        # Extract relevant data from the replay JSON
        squadrons = replay_data.get("squadrons", [])
        weather = replay_data.get("weather", "Unknown")
        time_of_day = replay_data.get("time_of_day", "Unknown")
        winner = replay_data.get("winning_team_squadron")
        #logging.info(winner)
        mission = replay_data.get("mission", "In Progress")
        teams = replay_data.get("teams", [])

        # Create the embed
        embed = discord.Embed(
            title=f"**{squadrons[0]} vs {squadrons[1]}**",
            #description=f"**👑 - {winner} **\nMap: {mission}\nTimeStamp: {timestamp}",
            description=f"**👑 • {winner}**\nMap: {mission}\nTimeStamp: {timestamp}\nGame ID: {session_id}",
            color=discord.Color.purple(),
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
            logging.info(f"Comp sent for session {session_id}")
            logging.info(f"[{timestamp}] FIND-COMP used by {user.name} (ID: {user.id}) in server '{server.name}' (ID: {server.id}) for username '{username}'")

            replay_file_path = f"replays/0{session_id}"
            if os.path.exists(replay_file_path):
                shutil.rmtree(replay_file_path)
                logging.info(f"Deleted replay folder: {replay_file_path}")
                
        except Exception as e:
            logging.error(f"Failed to send embed for session {session_id}: {e}")

    except Exception as e:
        logging.error(f"An error occurred in the find-comp command: {e}")
        await interaction.followup.send("An error occurred while processing the command. Please try again.")


@bot.tree.command(name="alarm", description="Set an alarm to monitor squadron changes")
@app_commands.describe(
    type="The type of alarm (e.g., Leave, Points, Logs)",
    channel_id="The ID of the channel to send alarm messages to",
    squadron_name="The FULL name of the squadron to monitor")
@commands.has_permissions(administrator=True)
async def alarm(interaction: discord.Interaction, type: str, channel_id: str,
                squadron_name: str):
    guild_id = interaction.guild.id
    key = f"{guild_id}-preferences.json"

    try:
        data = client.download_as_text(key)
        preferences = json.loads(data)
    except ObjectNotFoundError:
        preferences = {}
    except FileNotFoundError:
        preferences = {}

    if squadron_name not in preferences:
        preferences[squadron_name] = {}

    preferences[squadron_name][type] = channel_id

    client.upload_from_text(key, json.dumps(preferences))

    await interaction.response.send_message(
        f"Alarm of type '{type}' set for squadron '{squadron_name}' to send messages in channel ID {channel_id}.",
        ephemeral=True)


@bot.tree.command(name="sq-info", description="Fetch information about a squadron")
@app_commands.describe(
    squadron="The full name of the squadron to fetch information about",
    type=
    "The type of information to display: members, points, or leave empty for full info"
)
async def sq_info(interaction: discord.Interaction,
                  squadron: str = None,
                  type: str = None):
    await interaction.response.defer(ephemeral=False)

    try:
        # File to check for existing squadron data
        filename = "SQUADRONS.json"

        # Download existing squadron data
        try:
            squadrons_json = client.download_as_text(filename)
            squadrons = json.loads(squadrons_json)
        except:
            squadrons = {}

        guild_id = str(interaction.guild_id)

        # Check if a squadron is set for the server
        if not squadron and guild_id in squadrons:
            squadron = squadrons[guild_id]["SQ_LongHandName"]
        elif not squadron:
            embed = discord.Embed(
                title="Error",
                description=
                "No squadron specified and no squadron is set for this server.",
                color=discord.Color.red())
            embed.set_footer(text="Meow :3")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Fetch squadron information using the resolved squadron name
        embed = await fetch_squadron_info(squadron, type)
        if embed:
            embed.set_footer(text="Meow :3")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("Failed to fetch squadron info.",
                                            ephemeral=True)

    except Exception as e:
        logging.error(f"Error fetching squadron info: {e}")
        embed = discord.Embed(
            title="Error",
            description=
            f"An error occurred while fetching the squadron info: {e}",
            color=discord.Color.red())
        embed.set_footer(text="Meow :3")
        await interaction.followup.send(embed=embed, ephemeral=True)


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
    except:
        logging.warning(
            f"Leaderboard file for guild {guild_id} not found. Creating a new one."
        )

    # Ensure user_id is a string for consistent handling
    user_id_str = str(user_id)

    # Update the leaderboard
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


@bot.tree.command(name='set-squadron',
                  description='Set the squadron information for this server')
@app_commands.describe(
    sq_short_hand_name='The short name of the squadron to set',
    sq_long_hand_name='The long name of the squadron to set')
async def set_squadron(interaction: discord.Interaction,
                       sq_short_hand_name: str, sq_long_hand_name: str):
    try:
        # Defer the response to prevent timeouts
        await interaction.response.defer()

        # File to store squadron data
        filename = "SQUADRONS.json"

        # Download existing squadron data
        try:
            squadrons_json = client.download_as_text(filename)
            squadrons = json.loads(squadrons_json)
        except:
            logging.warning("SQUADRONS.json not found. Creating a new one."
                            )  # Nigh Impossible
            squadrons = {}

        # Ensure the server doesn't already have a different squadron set
        guild_id = str(interaction.guild_id)
        if guild_id in squadrons and squadrons[guild_id][
                'SQ_ShortHand_Name'] != re.sub(r'\W+', '', sq_short_hand_name):
            embed = discord.Embed(
                title="Error",
                description=
                f"This server already has a different squadron set: {squadrons[guild_id]['SQ_LongHandName']}.",
                color=discord.Color.red())
            embed.set_footer(text="Meow :3")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Sanitize and store the short-hand and long-hand names
        sq_short_hand_name = re.sub(r'\W+', '', sq_short_hand_name)
        sq_long_hand_name = re.sub(r'\W+', ' ', sq_long_hand_name)

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


@bot.tree.command(name='top',description='Get the top 20 squadrons with detailed stats')
async def top(interaction: discord.Interaction):
    await interaction.response.defer()

    squadron_data = await process_all_squadrons()

    if not squadron_data:
        await interaction.followup.send("No squadron data available.", ephemeral=True)
        return

    embed = discord.Embed(title="**Top 20 Squadrons**",
                          color=discord.Color.purple())

    for idx, squadron in enumerate(squadron_data, start=1):
        embed.add_field(
            name=f"**{idx} - {squadron['Short Name']}**",
            value=(
                f"**Squadron Score:** {squadron['Squadron Score']}\n"
                f"**Air Kills:** {squadron['Air Kills']}\n"
                f"**Ground Kills:** {squadron['Ground Kills']}\n"
                f"**Deaths:** {squadron['Deaths']}\n"
                f"**K/D:** {squadron['KD Ratio']}\n"
                f"**Playtime:** {squadron['Playtime']}\n"
                "\u200b"  # Adds a small amount of space between each squadron
            ),
            inline=True)

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


# Dictionary mapping flag emojis to language codes
LANGUAGE_MAP = {
    "🇷🇺": "ru",  # Russian
    "🇺🇸": "en",  # English (US)
    "🇬🇧": "en",  # English (UK)
    "🇪🇸": "es",  # Spanish
    "🇫🇷": "fr",  # French
    "🇩🇪": "de",  # German
    "🇨🇳": "zh-cn",  # Chinese (Simplified)
    "🇯🇵": "ja",  # Japanese
    "🇰🇷": "ko",  # Korean
    "🇮🇹": "it",  # Italian
    "🇵🇹": "pt",  # Portuguese
    "🇵🇱": "pl",  # Polish
    "🇱🇹": "lt",  # Lithuanian
    "🇱🇻": "lv",  # Latvian
    "🇪🇪": "et",  # Estonian
    "🇺🇦": "uk",  # Ukrainian
}


translator = Translator()
def perform_translation(text: str, target_language: str) -> str:
    try:
        translated = translator.translate(text, dest=target_language)
        return translated.text
    except Exception as e:
        logging.info(f"Translation failed: {e}")
        return "Translation error"


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    message = reaction.message  # The original message being reacted to
    text = message.content
    flag = reaction.emoji  # The flag emoji used
    guild_id = message.guild.id

    # Ignore reactions that are not in LANGUAGE_MAP
    if flag not in LANGUAGE_MAP:
        return  

    # Load server features
    features = await load_features(guild_id)
    if not features or features.get("Translate") != "True":
        embed = discord.Embed(
            title="Translation Disabled",
            description="Translations are not enabled for this server.\nUse /toggle 'Translate' to enable.",
            color=discord.Color.red()
        )
        #error_message = await message.channel.send(embed=embed)
        #await error_message.delete(delay=5)
        logging.info("Translation disabled!")
        return

    # Get target language from the dictionary
    target_language = LANGUAGE_MAP[flag]

    # Try to remove the user's reaction message to keep chat clean
    try:
        await reaction.message.remove_reaction(flag, user)
    except discord.Forbidden:
        pass  # Bot lacks permissions to remove reactions

    # Perform translation
    translated_text = perform_translation(text, target_language)

    if not translated_text:
        await message.channel.send(f"Translation failed for: {flag}", delete_after=5)
        return

    delete_timestamp = int(T.time()) + 38

    # Create embed
    embed = discord.Embed(
        title=f"**Translation ({target_language.upper()}):**", 
        color=discord.Color.purple()
    )
    embed.add_field(name=f"{translated_text}", value=f"Deleting <t:{delete_timestamp}:R>", inline=False)
    embed.set_footer(text=f"Meow • Requested by {user.display_name}")

    # Send embed and delete after 30 seconds
    sent_message = await message.channel.send(embed=embed)
    await sent_message.delete(delay=30)


@bot.tree.command(name="help", description="Get a guide on how to use the bot")
async def help(interaction: discord.Interaction):
    guide_text = (
        "**Commands Overview**\n"
        "1. **/alarm [type] [channel_id] [squadron_name]** - Set an alarm to monitor squadron changes.\n"
        "2. **/comp [username]** - Given a username, will attempt to detail the last found SQB game.\n"
        "3. **/stat [username]** - Get the ThunderSkill stats URL for a user.\n"
        "4. **/top** - Display the top 20 squadrons and their current stats.\n"
        "5. **/time-now** - Get the current UTC time and your local time.\n"
        "6. **/set-squadron {short hand} {long hand}** - Store squadron name for the discord server (used for logging).\n"
        "7. **/toggle** - Enable features like Translate (more to come soon).\n"
        "8. **/sq-info [squadron] [type]** - View the details of the specified squadron, if a squadron is set (command 6), it will default to that squadron.\n"
        "9. **/help** - Get a guide on how to use the bot.\n"
        "10. **Translation** - Put a flag reaction under a message to translate to that language (after using /enable).\n\n"
        "*For detailed information on each command, please read the input descriptions of each command, or reach out to not_so_toothless.*"
    )

    embed = discord.Embed(title="Bot Guide",
                          description=guide_text,
                          color=discord.Color.blue())
    embed.set_footer(text="Meow :3")
    await interaction.response.send_message(embed=embed, ephemeral=False)


bot.run(TOKEN)