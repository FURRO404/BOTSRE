# Standard Library Imports
import os
import sys
import json
import logging
import asyncio
from asyncio import *
import random
import datetime as DT
from datetime import datetime, time, timezone
import re
from io import StringIO

# Third-Party Library Imports
import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from discord import app_commands, ui, Interaction, SelectOption
from replit.object_storage import Client
from replit.object_storage.errors import ObjectNotFoundError
import requests

# Local Module Imports
from Meta_Add import add_to_metas
from Meta_Remove import remove_from_metas, find_vehicles_in_meta
from Scoreboard import Scoreboard
from permissions import grant_permission, revoke_permission, has_permission
import Alarms
from Games import guessing_game, choose_random_vehicle, normalize_name, randomizer_game
from SQ_Info import fetch_squadron_info
from AutoLog import fetch_games_for_user
from SQ_Info_Auto import process_all_squadrons
from Searcher import normalize_name, get_vehicle_type, get_vehicle_country, autofill_search
from Parse_Replay import save_replay_data

logging.basicConfig(level=logging.INFO)
client = Client(
    bucket_id="replit-objstore-b5261a8a-c768-4543-975e-dfce1cd7077d")

TOKEN = os.environ.get('DISCORD_KEY')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True
intents.dm_messages = True


class MyBot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix='~', intents=intents)
        self.synced = False
        self.conversations = {}  # Dictionary to track active conversations

    async def setup_hook(self):
        await self.tree.sync()
        self.synced = True


bot = MyBot()


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user} in the following guilds:')
    for guild in bot.guilds:
        print(f' - {guild.name} (id: {guild.id})')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.playing, name="War Thunder"))
    if not bot.synced:
        await bot.tree.sync()
        bot.synced = True
    snapshot_task.start()
    points_alarm_task.start()
    #logs_snapshot.start()


@bot.event
async def on_guild_join(guild):
    print(f'Joined new guild: {guild.name} (id: {guild.id})')
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

                    logging.info(f"squadron_preferences: {squadron_preferences}")
                    logging.info(f"key: {key}")
                    logging.info(f"Extracted channel_id: {channel_id}")

                    if channel_id:  # Ensure channel_id is not empty
                        try:
                            channel_id = int(channel_id)
                            channel = bot.get_channel(channel_id)
                            if channel:
                                for member, points in left_members.items():
                                    safe_member_name = discord.utils.escape_markdown(member)
                                    await channel.send(
                                        f"{safe_member_name} left {squadron_name} with {points} points"
                                    )
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
    if now_utc.hour == 22 and now_utc.minute == 10:
        region = "US"
        await execute_points_alarm_task(region)
    elif now_utc.hour == 7 and now_utc.minute == 10:
        region = "EU"
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
            sq_total_points = squadron_info.fields[0].value if squadron_info else "N/A"
            logging.info(f"{squadron_name} points at {sq_total_points}.")

            if "Points" in squadron_preferences:
                opposite_region = "EU" if region == "US" else "US"
                old_snapshot = Alarms.load_snapshot(guild_id, squadron_name,
                                                    opposite_region)
                new_snapshot = await Alarms.take_snapshot(squadron_name)

                if old_snapshot:
                    logging.info(
                        f"Loaded old snapshot for {squadron_name}, region {opposite_region}"
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

                                # Prepare the changes text by lines
                                changes_lines = []
                                for member, (points_change, current_points) in points_changes.items():
                                    safe_member_name = discord.utils.escape_markdown(member)
                                    arrow = "🔺" if points_change > 0 else "🔻"
                                    change_color = f"**{arrow} {abs(points_change)}**"

                                    changes_lines.append(f"{safe_member_name.ljust(20)} {change_color.ljust(10)} {current_points}")

                                # Chunk the lines into sections that fit within the max_field_length limit
                                max_field_length = 1024
                                chunks = []
                                current_chunk = "```\nName                 Change    Current Points\n"  # Header

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

                                # Create the embed and add fields for each chunk
                                embed = discord.Embed(
                                    title=f"**{squadron_name} {opposite_region} Points Update**",
                                    description=f"**Point Change:** {old_total_points} -> {sq_total_points}\n\n**Player Changes:**",
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


@tasks.loop(minutes=10)
async def logs_snapshot():
    logging.info("Running auto-logs")
    for guild in bot.guilds:
        guild_id = guild.id
        key = f"{guild_id}-preferences.json"
        logging.info(f"Processing guild: {guild_id}")

        try:
            data = client.download_as_text(key)
            preferences = json.loads(data)
            logging.info(f"Successfully loaded preferences for guild: {guild_id}")
        except (ObjectNotFoundError, FileNotFoundError):
            preferences = {}
            logging.warning(f"No preferences found for guild: {guild_id}")

        try:
            squadrons_data = client.download_as_text("SQUADRONS.json")
            squadrons = json.loads(squadrons_data)
            logging.info("Loaded SQUADRONS.json")
        except (ObjectNotFoundError, FileNotFoundError) as e:
            logging.error("SQUADRONS.json not found or could not be loaded")
            continue

        try:
            sessions_data = client.download_as_text("SESSIONS.json")
            logging.info(f"Successfully loaded Session Data")
            sessions = json.loads(sessions_data)
        except (ObjectNotFoundError, FileNotFoundError):
            logging.info("SESSIONS.json not found, creating a new one.")
            sessions = {}

        # Check if the guild_id exists in sessions.json, if not, create an empty list
        if str(guild_id) not in sessions:
            sessions[str(guild_id)] = []
            logging.info(f"Added new guild entry for guild: {guild_id} in sessions.json")

        all_found_sessions = []  # Collect all sessions found for this guild

        # Iterate through the preferences to check if logging is set up
        for squadron_name, squadron_preferences in preferences.items():
            if "Logs" in squadron_preferences:
                logging.info(f"Logs are enabled for squadron: {squadron_name} in guild: {guild_id}")
                shortname = get_shortname_from_long(squadron_name)
                squadron_info = await fetch_squadron_info(squadron_name, embed_type="logs")

                found_sessions = []
                if squadron_info:
                    for field in squadron_info.fields:
                        usernames = field.value.split("\n")
                        for username in usernames:
                            games = await fetch_games_for_user(username)
                            for game in games:
                                session_id = game.get("sessionIdHex")
                                if session_id and session_id not in sessions[str(guild_id)]:
                                    found_sessions.append(session_id)

                # Count occurrences of each session_id in found_sessions
                session_counts = {}
                for session in found_sessions:
                    session_counts[session] = session_counts.get(session, 0) + 1

                # Collect sessions that appear more than 3 times
                valid_sessions = [session for session, count in session_counts.items() if count >= 3]
                logging.info(f"Valid session IDs (found 3 or more times): {valid_sessions}")

                all_found_sessions.extend(found_sessions)  # Add found sessions to the overall list

                # Process valid sessions concurrently
                await asyncio.gather(
                    *[
                        process_session(bot, session_id, guild_id, squadron_preferences)
                        for session_id in valid_sessions
                    ]
                )

        # After processing all squadrons, update the sessions.json with the found sessions
        if all_found_sessions:
            existing_sessions = sessions.get(str(guild_id), [])
            updated_sessions = list(set(existing_sessions + all_found_sessions))  # Remove duplicates
            sessions[str(guild_id)] = updated_sessions

            # Upload the updated sessions.json file back to storage
            client.upload_from_text("SESSIONS.json", json.dumps(sessions, indent=4))
            logging.info(f"Updated SESSIONS.json for guild {guild_id} with new sessions: {all_found_sessions}")


async def process_session(bot, session_id, guild_id, squadron_preferences):
    """Processes a single session, saves replay data, and sends embeds to the specified Discord channel."""
    await save_replay_data(session_id)

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

    squadrons = replay_data.get("squadrons", [])
    weather = replay_data.get("weather", "Unknown")
    time_of_day = replay_data.get("time_of_day", "Unknown")
    winner = "MEOW"
    teams = replay_data.get("teams", [])

    embed = discord.Embed(
        title=f"**{squadrons[0]} vs {squadrons[1]}**",
        description=f"Weather: {weather}\nTime of Day: {time_of_day}\nWinner: {winner}\nGame ID: {session_id}",
        color=discord.Color.blue(),
    )

    for team in teams:
        squadron_name = team.get("squadron", "Unknown")
        players = team.get("players", [])

        player_details = "\n".join(
            f"{escape_markdown(player['nick'])} ({player['vehicle']})"
            for player in players
        )

        embed.add_field(name=f"{squadron_name}", value=player_details or "No players found.", inline=False)

    channel_id = squadron_preferences.get("Logs", "")
    channel_id = int(channel_id.strip("<#>"))
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
            logging.info(f"Embed sent for session {session_id} in guild {guild_id}")
        else:
            logging.warning(f"Channel ID {channel_id} not found in guild {guild_id}")
    except Exception as e:
        logging.error(f"Failed to send embed for session {session_id}: {e}")



@logs_snapshot.before_loop
async def before_logs_snapshot():
    await bot.wait_until_ready()

@bot.tree.command(name='find-comp', description='Find the last known comp for a given team')
@app_commands.describe(username='The username of an enemy player')
async def find_comp(interaction: discord.Interaction, username: str):
    await interaction.response.defer()  # Defer response to handle potential long-running operations
    logging.info(f"Running FIND-COMP for username {username}")

    try:
        # Fetch games for the given username
        games = await fetch_games_for_user(username)
        if not games:
            await interaction.followup.send(f"No games found for user `{username}`.")
            return

        # Process the first game (you can adjust to loop through games if needed)
        game = games[0]
        session_id = game.get('sessionIdHex')
        if not session_id:
            await interaction.followup.send(f"Could not retrieve session ID for user `{username}`.")
            return

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
        winner = replay_data.get("winner", "Unknown")
        teams = replay_data.get("teams", [])

        # Create the embed
        embed = discord.Embed(
            title=f"**{squadrons[0]} vs {squadrons[1]}**",
            description=f"Weather: {weather}\nTime of Day: {time_of_day}\nWinner: {winner}\nGame ID: {session_id}",
            color=discord.Color.blue(),
        )

        for team in teams:
            squadron_name = team.get("squadron", "Unknown")
            players = team.get("players", [])

            player_details = "\n".join(
                f"{escape_markdown(player['nick'])} ({player['vehicle']})"
                for player in players
            )

            embed.add_field(name=f"{squadron_name}", value=player_details or "No players found.", inline=False)

        
        try:
            await interaction.followup.send(embed=embed)
            logging.info(f"Comp sent for session {session_id}")
        except Exception as e:
            logging.error(f"Failed to send embed for session {session_id}: {e}")

    except Exception as e:
        logging.error(f"An error occurred in the find-comp command: {e}")
        await interaction.followup.send("An error occurred while processing the command. Please try again.")



@bot.tree.command(name="alarm",
                  description="Set an alarm to monitor squadron changes")
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


@bot.tree.command(name="grant", description="Grant a user or role permission")
@app_commands.describe(
    target="The user or role to grant permission to",
    permission_type="The type of permission (Session or Meta)")
@commands.has_permissions(administrator=True)
async def grant(interaction: discord.Interaction, target: str,
                permission_type: str):
    if permission_type not in ["Session", "Meta"]:
        await interaction.response.send_message(
            "Invalid permission type. Use 'Session' or 'Meta'.",
            ephemeral=True)
        return

    is_role = False
    target_id = None
    target_obj = None

    if target.startswith("<@&"):  # Check if target is a role
        is_role = True
        try:
            target_id = int(target[3:-1])
        except ValueError:
            await interaction.response.send_message("Invalid role ID format.",
                                                    ephemeral=True)
            return
        target_obj = interaction.guild.get_role(target_id)
    elif target.startswith("<@"):  # Check if target is a user
        try:
            target_id = int(target[2:-1])
        except ValueError:
            await interaction.response.send_message("Invalid user ID format.",
                                                    ephemeral=True)
            return
        target_obj = interaction.guild.get_member(target_id)

    if not target_obj:
        await interaction.response.send_message("Invalid user or role.",
                                                ephemeral=True)
        return

    grant_permission(target_id, permission_type, interaction.guild.id, is_role)
    await interaction.response.send_message(
        f"Granted {permission_type} permission to {target}.", ephemeral=True)


@bot.tree.command(name="revoke",
                  description="Revoke a user or role's permission")
@app_commands.describe(
    target="The user or role to revoke permission from",
    permission_type="The type of permission (Session or Meta)")
@commands.has_permissions(administrator=True)
async def revoke(interaction: discord.Interaction, target: str,
                 permission_type: str):
    if permission_type not in ["Session", "Meta"]:
        await interaction.response.send_message(
            "Invalid permission type. Use 'Session' or 'Meta'.",
            ephemeral=True)
        return

    is_role = False
    target_id = None
    target_obj = None

    if target.startswith("<@&"):  # Check if target is a role
        is_role = True
        try:
            target_id = int(target[3:-1])
        except ValueError:
            await interaction.response.send_message("Invalid role ID format.",
                                                    ephemeral=True)
            return
        target_obj = interaction.guild.get_role(target_id)
    elif target.startswith("<@"):  # Check if target is a user
        try:
            target_id = int(target[2:-1])
        except ValueError:
            await interaction.response.send_message("Invalid user ID format.",
                                                    ephemeral=True)
            return
        target_obj = interaction.guild.get_member(target_id)

    if not target_obj:
        await interaction.response.send_message("Invalid user or role.",
                                                ephemeral=True)
        return

    revoke_permission(target_id, permission_type, interaction.guild.id,
                      is_role)
    await interaction.response.send_message(
        f"Revoked {permission_type} permission from {target}.", ephemeral=True)


def has_roles_or_admin(permission_type):
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id == bot.owner_id:
            return True
        if interaction.user.guild_permissions.administrator:
            return True
        if has_permission(interaction.user.id, interaction.user.roles,
                          permission_type, interaction.guild.id):
            return True
        return False

    return app_commands.check(predicate)


GROUND_DATA_FILE = 'DATA/Ground.txt'
AIR_DATA_FILE = 'DATA/Air.txt'

# Hardcoded BR options including more values
BR_OPTIONS = [
    "4.3", "4.7", "5.0", "5.3", "5.7", "6.0", "6.3", "6.7", "7.0", "7.3",
    "7.7", "8.0", "8.3", "8.7", "9.0", "9.3", "9.7", "10.0", "10.3", "10.7",
    "11.0", "11.3", "11.7", "12.0", "12.3", "12.7", "13.0", "13.3", "13.7", "14.0"
]


def get_country_flag(country):
    flags = {
        "USSR": "🇷🇺",
        "Germany": "🇩🇪",
        "USA": "🇺🇸",
        "Great Britain": "🇬🇧",
        "Japan": "🇯🇵",
        "Italy": "🇮🇹",
        "France": "🇫🇷",
        "China": "🇨🇳",
        "Sweden": "🇸🇪",
        "Israel": "🇮🇱"
    }
    return flags.get(country, "")


def view_metalist(br: str, server_id: int) -> discord.Embed:
    key = f"{server_id}_METAS.txt"

    try:
        data = client.download_as_text(key)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return discord.Embed(title="Meta List",
                                 description="Meta is empty.",
                                 color=discord.Color.red())
        else:
            logging.error(
                f"Error loading meta data for server {server_id}: {e}")
            return discord.Embed(
                title="Meta List",
                description=
                "An error occurred while trying to view the Meta list.",
                color=discord.Color.red())
    except Exception as e:
        logging.error(f"Error loading meta data for server {server_id}: {e}")
        return discord.Embed(
            title="Meta List",
            description="There is no Meta list for this server.",
            color=discord.Color.red())

    metas = json.loads(data)

    if not metas:
        return discord.Embed(
            title="Meta List",
            description=f"No vehicles found at BR {br} in Meta.",
            color=discord.Color.red())

    if br not in metas:
        return discord.Embed(
            title="Meta List",
            description=f"No vehicles found at BR {br} in Meta.",
            color=discord.Color.red())

    categorized_vehicles = {
        'Ground Forces': [],
        'Anti-Aircraft': [],
        'Air Forces': [],
        'Helis': []
    }

    for vehicle in metas[br]:
        vehicle_type = get_vehicle_type(vehicle)
        if vehicle_type:
            country = get_vehicle_country(vehicle)
            flag = get_country_flag(country)
            vehicle_display = f"• {vehicle} ({flag})"

            if 'Light tank' in vehicle_type or 'Medium tank' in vehicle_type or 'Heavy tank' in vehicle_type or 'Tank destroyer' in vehicle_type:
                categorized_vehicles['Ground Forces'].append(vehicle_display)
            elif 'SPAA' in vehicle_type:
                categorized_vehicles['Anti-Aircraft'].append(vehicle_display)
            elif 'helicopter' in vehicle_type.lower():
                categorized_vehicles['Helis'].append(vehicle_display)
            else:
                categorized_vehicles['Air Forces'].append(vehicle_display)

    embed = discord.Embed(title=f"Meta List for BR {br}",
                          color=discord.Color.blue())
    for category, vehicles in categorized_vehicles.items():
        if vehicles:
            embed.add_field(name=category,
                            value="\n".join(vehicles),
                            inline=False)
    embed.set_footer(text="Meow :3")
    return embed


class InitialView(discord.ui.View):

    def __init__(self, interaction):
        super().__init__()
        self.interaction = interaction
        self.add_item(InitialDropdown(interaction))


class InitialDropdown(discord.ui.Select):

    def __init__(self, interaction):
        options = [
            discord.SelectOption(label="Add"),
            discord.SelectOption(label="Remove"),
            discord.SelectOption(label="View")
        ]
        super().__init__(placeholder="Choose an action...", options=options)
        self.interaction = interaction

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] in ["Add", "Remove"]:
            if not has_permission(
                    interaction.user.id, interaction.user.roles, "Meta",
                    interaction.guild.id
            ) and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(
                    "You do not have permission to perform this action.",
                    ephemeral=True)
                return

        if self.values[0] == "Add":
            await interaction.response.send_modal(AddModal(interaction))
        elif self.values[0] == "Remove":
            await interaction.response.send_modal(RemoveModal(interaction))
        elif self.values[0] == "View":
            await interaction.response.send_message(
                "Select BRs to view:", view=BRSelectView(interaction))
        else:
            await interaction.response.send_message("Invalid action selected.",
                                                    ephemeral=True)


class AddModal(discord.ui.Modal, title="Add Item"):

    def __init__(self, interaction):
        super().__init__()
        self.interaction = interaction
        self.add_item(discord.ui.TextInput(label="Enter item to search for"))

    async def on_submit(self, interaction: discord.Interaction):
        search_term = self.children[0].value.lower(
        )  # Convert search term to lowercase

        # Read and search both files
        matches = set()
        for file_path in [GROUND_DATA_FILE, AIR_DATA_FILE]:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                matches.update(
                    normalize_name(line.strip()) for line in lines
                    if search_term in line.lower()
                )  # Convert each line to lowercase for comparison

        matches = list(matches)  # Convert back to list to allow indexing

        if not matches:
            await interaction.response.send_message(
                f"No matches found for '{search_term}'.", ephemeral=True)
        elif len(matches) == 1:
            view = BRSelectionView(matches[0])
            await interaction.response.send_message(
                f"Select BRs for '{matches[0]}':", view=view)
        else:
            view = MatchSelectionView(matches)
            await interaction.response.send_message(
                "Multiple matches found, please select one:", view=view)


class MatchSelectionView(discord.ui.View):

    def __init__(self, matches):
        super().__init__()
        self.matches = matches
        self.add_match_dropdowns()

    def add_match_dropdowns(self):
        options_chunks = [
            self.matches[i:i + 25] for i in range(0, len(self.matches), 25)
        ]
        for options_chunk in options_chunks:
            self.add_item(MatchSelectionDropdown(options_chunk))


class MatchSelectionDropdown(discord.ui.Select):

    def __init__(self, matches):
        options = [discord.SelectOption(label=match) for match in matches]
        super().__init__(placeholder="Select a match...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_match = self.values[0]
        view = BRSelectionView(selected_match)
        await interaction.response.send_message(
            f"Select BRs for '{selected_match}':", view=view)


class BRSelectionView(discord.ui.View):

    def __init__(self, selected_match):
        super().__init__()
        self.selected_match = selected_match
        self.add_br_dropdowns()

    def add_br_dropdowns(self):
        options_chunks = [
            BR_OPTIONS[i:i + 25] for i in range(0, len(BR_OPTIONS), 25)
        ]
        for options_chunk in options_chunks:
            self.add_item(
                BRSelectionDropdown(self.selected_match, options_chunk))


class BRSelectionDropdown(discord.ui.Select):

    def __init__(self, selected_match, options):
        options = [discord.SelectOption(label=br) for br in options]
        super().__init__(
            placeholder="Select BRs...",
            options=options,
            min_values=1,
            max_values=len(options)  # Allow multiple selections
        )
        self.selected_match = selected_match

    async def callback(self, interaction: discord.Interaction):
        selected_brs = self.values

        await interaction.response.defer(
        )  # Defer the response to avoid timeouts

        response_messages = []

        for br in selected_brs:
            response = add_to_metas(self.selected_match, br,
                                    interaction.guild.id)
            response_messages.append(response)

        # Create an embed for the response
        embed = discord.Embed(
            title=f"Add to Meta",
            description=f"Results for adding '{self.selected_match}'",
            color=discord.Color.green())
        for message in response_messages:
            embed.add_field(name="Result", value=message, inline=False)

        await interaction.followup.send(embed=embed)


class RemoveModal(discord.ui.Modal, title="Remove Item"):

    def __init__(self, interaction):
        super().__init__()
        self.interaction = interaction
        self.add_item(discord.ui.TextInput(label="Enter item to search for"))

    async def on_submit(self, interaction: discord.Interaction):
        search_term = self.children[0].value.lower(
        )  # Convert search term to lowercase
        server_id = interaction.guild.id

        # Find vehicles in the meta data
        matches = find_vehicles_in_meta(search_term, server_id)

        if not matches:
            await interaction.response.send_message(
                f"No matches found for '{search_term}' in meta data.",
                ephemeral=True)
        else:
            view = RemoveMatchSelectionView(matches, search_term)
            await interaction.response.send_message(
                f"Select the vehicle to remove:", view=view)


class RemoveMatchSelectionView(discord.ui.View):

    def __init__(self, matches, search_term):
        super().__init__()
        self.matches = matches
        self.search_term = search_term
        self.add_match_dropdowns()

    def add_match_dropdowns(self):
        options_chunks = [
            list(self.matches.keys())[i:i + 25]
            for i in range(0, len(self.matches), 25)
        ]
        for options_chunk in options_chunks:
            self.add_item(
                RemoveMatchSelectionDropdown(self.search_term, self.matches,
                                             options_chunk))


class RemoveMatchSelectionDropdown(discord.ui.Select):

    def __init__(self, search_term, matches, options):
        options = [discord.SelectOption(label=vehicle) for vehicle in options]
        super().__init__(placeholder="Select a vehicle...", options=options)
        self.search_term = search_term
        self.matches = matches

    async def callback(self, interaction: discord.Interaction):
        selected_vehicle = self.values[0]
        view = RemoveBRSelectionView(self.matches[selected_vehicle],
                                     selected_vehicle)
        await interaction.response.send_message(
            f"Select BRs to remove '{selected_vehicle}' from:", view=view)


class RemoveBRSelectionView(discord.ui.View):

    def __init__(self, brs, selected_vehicle):
        super().__init__()
        self.selected_vehicle = selected_vehicle
        self.brs = brs
        self.add_br_dropdowns()

    def add_br_dropdowns(self):
        options_chunks = [
            self.brs[i:i + 25] for i in range(0, len(self.brs), 25)
        ]
        for options_chunk in options_chunks:
            self.add_item(
                RemoveBRSelectionDropdown(self.selected_vehicle,
                                          options_chunk))


class RemoveBRSelectionDropdown(discord.ui.Select):

    def __init__(self, selected_vehicle, options):
        options = [discord.SelectOption(label=br) for br in options]
        super().__init__(
            placeholder="Select BRs...",
            options=options,
            min_values=1,
            max_values=len(options)  # Allow multiple selections
        )
        self.selected_vehicle = selected_vehicle

    async def callback(self, interaction: discord.Interaction):
        selected_brs = self.values
        # Log the details
        logging.debug(
            f"Item: {self.selected_vehicle} removed from BRs: {selected_brs}")

        response_messages = []

        # Remove the vehicle from each selected BR using meta_remove
        for br in selected_brs:
            response = remove_from_metas(self.selected_vehicle, br,
                                         interaction.guild.id)
            logging.info(response)
            response_messages.append(response)

        # Create an embed for the response
        embed = discord.Embed(
            title=f"Remove from Meta",
            description=f"Results for removing '{self.selected_vehicle}'",
            color=discord.Color.red())
        for message in response_messages:
            embed.add_field(name="Result", value=message, inline=False)

        await interaction.response.send_message(embed=embed)


class BRSelectView(discord.ui.View):

    def __init__(self, interaction):
        super().__init__()
        self.interaction = interaction
        self.add_br_dropdowns()

    def add_br_dropdowns(self):
        key = f"{self.interaction.guild.id}_METAS.txt"

        try:
            data = client.download_as_text(key)
            metas = json.loads(data)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                metas = {}
            else:
                logging.error(
                    f"Error loading meta data for server {self.interaction.guild.id}: {e}"
                )
                metas = {}
        except Exception as e:
            logging.error(
                f"Error loading meta data for server {self.interaction.guild.id}: {e}"
            )
            metas = {}

        # Sort BR options numerically
        br_options = sorted(metas.keys(), key=lambda x: float(x))
        options_chunks = [
            br_options[i:i + 25] for i in range(0, len(br_options), 25)
        ]
        for options_chunk in options_chunks:
            self.add_item(BRSelectDropdown(options_chunk))


class BRSelectDropdown(discord.ui.Select):

    def __init__(self, options):
        options = [discord.SelectOption(label=br) for br in options]
        super().__init__(
            placeholder="Select BRs to view...",
            options=options,
            min_values=1,
            max_values=len(options)  # Allow multiple selections
        )

    async def callback(self, interaction: discord.Interaction):
        selected_brs = self.values

        await interaction.response.defer(
        )  # Defer the response to avoid timeouts

        embeds = [
            view_metalist(br, interaction.guild.id) for br in selected_brs
        ]

        for embed in embeds:
            await interaction.followup.send(embed=embed)


@bot.tree.command(name="console", description="Choose an action.")
async def console(interaction: discord.Interaction):
    view = InitialView(interaction)
    await interaction.response.send_message("Choose an action:", view=view)


@bot.tree.command(name="viewmeta", description="View the meta list.")
@app_commands.describe()
async def viewmeta(interaction: discord.Interaction):
    # This will mimic the "View" action from the console dropdown.
    view = BRSelectView(interaction)
    await interaction.response.send_message("Select BRs to view:", view=view)


@bot.tree.command(name="clear", description="Clear the entire Meta list")
@commands.is_owner()
async def clear(interaction: discord.Interaction):
    if not await bot.is_owner(interaction.user):
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True)
        return
    try:
        key = f"{interaction.guild.id}_METAS.txt"
        client.upload_from_text(key, json.dumps(
            {}))  # Clear the file by uploading an empty JSON object
        embed = discord.Embed(title="Meta List Cleared",
                              description="The Meta list has been cleared.",
                              color=discord.Color.yellow())
        embed.set_footer(text="Meow :3")
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        logging.error(f"Error clearing Meta list: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(f"An error occurred: {e}",
                                                    ephemeral=True)


@bot.tree.command(name="session", description="Start a new session")
@has_roles_or_admin("Session")
async def session(interaction: discord.Interaction):
    current_time = DT.datetime.utcnow().time()
    if current_time >= DT.time(14, 0) and current_time <= DT.time(22, 0):
        region = "EU"
    elif current_time >= DT.time(1, 0) and current_time <= DT.time(7, 0):
        region = "US"
    else:
        region = "TEST"

    # Defer the interaction to avoid timing out
    await interaction.response.defer(ephemeral=True)

    logging.debug(f"Starting session in region: {region}")

    try:
        await Scoreboard.start_session(interaction, region)
        await interaction.followup.send("Session started.", ephemeral=True)

    except discord.errors.InteractionResponded:
        logging.error(
            "Interaction has already been responded to. Skipping response.")

    except discord.errors.NotFound as e:
        logging.error(f"Interaction Not Found (404): {e}")
        await interaction.followup.send(
            f"Session started, but an error occurred: {e}", ephemeral=True)

    except discord.errors.HTTPException as e:
        logging.error(f"HTTPException: {e}")
        await interaction.followup.send(f"HTTP error occurred: {e}",
                                        ephemeral=True)

    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        await interaction.followup.send(f"An unexpected error occurred: {e}",
                                        ephemeral=True)


@bot.tree.command(name="setcomp", description="Set your current team lineup")
@app_commands.describe(vehicle1="Name of Vehicle 1",
                       vehicle2="Name of Vehicle 2",
                       vehicle3="Name of Vehicle 3",
                       vehicle4="Name of Vehicle 4",
                       vehicle5="Name of Vehicle 5",
                       vehicle6="Name of Vehicle 6",
                       vehicle7="Name of Vehicle 7",
                       vehicle8="Name of Vehicle 8")
@has_roles_or_admin("Session")
async def setComp(interaction: discord.Interaction, vehicle1: str,
                  vehicle2: str, vehicle3: str, vehicle4: str, vehicle5: str,
                  vehicle6: str, vehicle7: str, vehicle8: str):
    await interaction.response.defer(ephemeral=True)

    try:
        await handle_comp_command(interaction, vehicle1, vehicle2, vehicle3,
                                  vehicle4, vehicle5, vehicle6, vehicle7,
                                  vehicle8)
    except Exception as e:
        logging.error(f"Error setting team comp: {e}")
        await interaction.followup.send(f"An error occurred: {e}",
                                        ephemeral=True)


@bot.tree.command(name="win", description="Log a win for a team")
@app_commands.describe(team_name="The name of the team",
                       bombers="Number of bombers",
                       fighters="Number of fighters",
                       helis="Number of helicopters",
                       tanks="Number of tanks",
                       spaa="Number of anti-aircraft",
                       comment="Additional comments")
@has_roles_or_admin("Session")
async def win(interaction: discord.Interaction,
              team_name: str,
              bombers: int,
              fighters: int,
              helis: int,
              tanks: int,
              spaa: int,
              comment: str = ""):
    # Defer the interaction
    await interaction.response.defer(ephemeral=True)

    try:
        await Scoreboard.log_win(interaction, team_name, bombers, fighters,
                                 helis, tanks, spaa, comment)
        await interaction.followup.send("Win logged.", ephemeral=True)

    except Exception as e:
        logging.error(f"Error logging win: {e}")
        await interaction.followup.send(f"An error occurred: {e}",
                                        ephemeral=True)


@bot.tree.command(name="loss", description="Log a loss for a team")
@app_commands.describe(team_name="The name of the team",
                       bombers="Number of bombers",
                       fighters="Number of fighters",
                       helis="Number of helicopters",
                       tanks="Number of tanks",
                       spaa="Number of anti-aircraft",
                       comment="Additional comments")
@has_roles_or_admin("Session")
async def loss(interaction: discord.Interaction,
               team_name: str,
               bombers: int,
               fighters: int,
               helis: int,
               tanks: int,
               spaa: int,
               comment: str = ""):
    # Defer the interaction
    await interaction.response.defer(ephemeral=True)

    try:
        await Scoreboard.log_loss(interaction, team_name, bombers, fighters,
                                  helis, tanks, spaa, comment)
        await interaction.followup.send("Loss logged.", ephemeral=True)

    except Exception as e:
        logging.error(f"Error logging loss: {e}")
        await interaction.followup.send(f"An error occurred: {e}",
                                        ephemeral=True)


@bot.tree.command(name="end", description="End the current session")
@has_roles_or_admin("Session")
async def end(interaction: discord.Interaction):
    # Defer the interaction to avoid timing out
    await interaction.response.defer(ephemeral=True)

    try:
        await Scoreboard.end_session(interaction, bot)
        await interaction.followup.send("Session ended.", ephemeral=True)

    except Exception as e:
        logging.error(f"Error ending session: {e}")
        await interaction.followup.send(f"An error occurred: {e}",
                                        ephemeral=True)


@bot.tree.command(name="edit",
                  description="Edit the details of the last logged game")
@app_commands.describe(status="The status of the game (W for win, L for loss)",
                       team_name="The name of the team",
                       bombers="Number of bombers",
                       fighters="Number of helicopters",
                       helis="Number of helicopters",
                       tanks="Number of tanks",
                       spaa="Number of anti-aircraft",
                       comment="Additional comments")
@has_roles_or_admin("Session")
async def edit(interaction: discord.Interaction,
               status: str,
               team_name: str,
               bombers: int,
               fighters: int,
               helis: int,
               tanks: int,
               spaa: int,
               comment: str = ""):
    await interaction.response.defer(ephemeral=True
                                     )  # Defer the interaction response

    try:
        await Scoreboard.edit_game(interaction, status, team_name, bombers,
                                   fighters, helis, tanks, spaa, comment)
        await interaction.followup.send("Last game edited.", ephemeral=True)
    except Exception as e:
        logging.error(f"Error editing game: {e}")
        await interaction.followup.send(f"An error occurred: {e}",
                                        ephemeral=True)


@bot.tree.command(name="sq-info",
                  description="Fetch information about a squadron")
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


active_guessing_games = {
}  # Dictionary to keep track of active guessing games by channel ID


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


@bot.tree.command(name='guessing-game', description='Start a guessing game')
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


@bot.tree.command(name='leaderboard', description='Show the leaderboard')
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


@bot.tree.command(name="trivia",
                  description="Play a War Thunder vehicle trivia game")
@app_commands.describe(
    difficulty="Choose the difficulty level: easy, medium, or hard")
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


def categorize_vehicle(vehicle_type):
    if vehicle_type:
        vehicle_type_lower = vehicle_type.lower()
        if 'tank' in vehicle_type_lower:
            return 'Ground Forces'
        elif 'spaa' in vehicle_type_lower:
            return 'Anti-Aircraft'
        elif 'helicopter' in vehicle_type_lower:
            return 'Helis'
        elif 'bomber' in vehicle_type_lower:
            return 'Bombers'
        else:
            return 'Air Forces'
    return 'Unknown'


async def handle_attachment(interaction: discord.Interaction,
                            attachment: discord.Attachment, enemy_team: str,
                            message: discord.Message, result_type: str,
                            comment: str):
    guild_id = interaction.guild.id
    user_id = interaction.user.id

    # Load the user's session
    Scoreboard.load_session(guild_id, user_id)
    session = Scoreboard.sessions.get((guild_id, user_id))

    if session is None or not session["started"]:
        await interaction.followup.send(
            "No active session found. Please start a session first.",
            ephemeral=True)
        return

    if attachment.filename.endswith('.txt'):
        logs_text = await attachment.read()
        logs_text = logs_text.decode('utf-8')

        # Validate JSON format
        try:
            logs = json.loads(logs_text)
        except json.JSONDecodeError as e:
            await interaction.followup.send(f"Invalid JSON format: {e}",
                                            ephemeral=True)
            return

        # Save logs to a file
        with open('input.txt', 'w', encoding='utf-8') as f:
            f.write(logs_text)

        # Redirect stdout to capture the output
        original_stdout = sys.stdout
        sys.stdout = StringIO()  # Capture the output in a StringIO object

        try:
            # Load logs and process them
            logs = read_logs_from_file('input.txt')
            logs['damage'].reverse()  # Reverse the order of the logs
            games, _ = separate_games(logs['damage'])

            if games:
                parsed_events, clan_members = parse_logs(games[0], enemy_team)
                categorized_vehicles = {
                    'Ground Forces': 0,
                    'Anti-Aircraft': 0,
                    'Helis': 0,
                    'Bombers': 0,
                    'Air Forces': 0,
                    'Unknown': 0
                }

                for event in parsed_events:
                    print(event)
                print("\nClan Members Vehicles:")
                for member in clan_members:
                    vehicle_name = member.split(': ')[1].strip('()')
                    normalized_vehicle_name = normalize_name(vehicle_name)
                    autofilled_vehicle_name = autofill_search(
                        normalized_vehicle_name)
                    vehicle_type = get_vehicle_type(autofilled_vehicle_name)
                    category = categorize_vehicle(vehicle_type)
                    categorized_vehicles[category] += 1
                    print(
                        f"{member} - Autofilled: {autofilled_vehicle_name} - Type: {vehicle_type}"
                    )

                # Prepare counts for each category
                bombers = categorized_vehicles['Bombers']
                fighters = categorized_vehicles['Air Forces']
                helis = categorized_vehicles['Helis']
                tanks = categorized_vehicles['Ground Forces']
                spaa = categorized_vehicles['Anti-Aircraft']

                if result_type == 'win':
                    await Scoreboard.log_win(interaction, enemy_team, bombers,
                                             fighters, helis, tanks, spaa,
                                             comment)
                    await interaction.followup.send("Win logged.",
                                                    ephemeral=True)
                elif result_type == 'loss':
                    await Scoreboard.log_loss(interaction, enemy_team, bombers,
                                              fighters, helis, tanks, spaa,
                                              comment)
                    await interaction.followup.send("Loss logged.",
                                                    ephemeral=True)
            else:
                print("No games found.")

            # Get the captured output
            captured_output = sys.stdout.getvalue()
        finally:
            # Restore the original stdout
            sys.stdout = original_stdout

        # Send the captured output to the console
        print(captured_output)

        # Delete the user's message containing the attachment
        await message.delete()
    else:
        await interaction.followup.send("Please upload a valid .txt file.",
                                        ephemeral=True)


@bot.tree.command(name='quick-log',
                  description='Process game logs with status and enemy team')
@app_commands.describe(status='Win or Loss (W/L)',
                       enemy_team='Name of the enemy team',
                       comment='Additional comments')
@has_roles_or_admin("Session")
async def quick_log(interaction: discord.Interaction,
                    status: str,
                    enemy_team: str,
                    comment: str = ""):
    # Ensure status is either 'W' or 'L'
    if status not in ['W', 'L']:
        await interaction.response.send_message(
            "Invalid status value. Please use 'W' or 'L'.", ephemeral=True)
        return

    result_type = 'win' if status == 'W' else 'loss'
    await interaction.response.send_message(
        "Click this [link](http://localhost:8111/hudmsg?lastEvt=0&lastDmg=0), copy all contents, and paste them back below this message.",
        ephemeral=True)

    # Check for message attachments
    def check(msg):
        return msg.author == interaction.user and len(msg.attachments) > 0

    message = await bot.wait_for('message', check=check)
    if message.attachments:
        await handle_attachment(interaction, message.attachments[0],
                                enemy_team, message, result_type, comment)


@bot.tree.command(name='time',
                  description='Get the current UTC and local time')
async def time(interaction: discord.Interaction):
    utc_time = DT.datetime.utcnow().strftime('%I:%M %p')
    timestamp = int(DT.datetime.utcnow().timestamp())

    embed = discord.Embed(
        title="Current UTC and local Time",
        description=
        f"**UTC Time:** {utc_time}\n**Local Time:** <t:{timestamp}:t>",
        color=discord.Color.blue())
    embed.set_footer(text="Meow :3")

    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name="randomizer",
                  description="Choose a random vehicle and its BR.")
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
@has_roles_or_admin("Session")
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


@bot.tree.command(name='top',
                  description='Get the top 20 squadrons with detailed stats')
async def top(interaction: discord.Interaction):
    await interaction.response.defer()

    squadron_data = process_all_squadrons()

    if not squadron_data:
        await interaction.followup.send("No squadron data available.",
                                        ephemeral=True)
        return

    embed = discord.Embed(title="**Top 20 Squadrons**",
                          color=discord.Color.purple())

    for idx, squadron in enumerate(squadron_data, start=1):
        embed.add_field(
            name=f"**{idx} - {squadron['Squadron Name']}**",
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



@bot.tree.command(name="help", description="Get a guide on how to use the bot")
async def help(interaction: discord.Interaction):
    guide_text = (
        "**Commands Overview**\n"
        "1. **/grant [target] [permission_type]** - Grant a user or role permission.\n"
        "2. **/revoke [target] [permission_type]** - Revoke a user or role permission.\n"
        "3. **/clear** - Clear the entire Meta list (Owner only).\n"
        "4. **/session** - Start a new session.\n"
        "5. **/randomizer** - returns a random vehicle at its BR.\n"
        "6. **/alarm [type] [channel_id] [squadron_name]** - Set an alarm to monitor squadron changes.\n"
        "7. **/stat [username]** - Get the ThunderSkill stats URL for a user.\n"
        "8. **/guessing-game** - Start a guessing game.\n"
        "9. **/trivia [difficulty]** - Play a War Thunder vehicle trivia game. A higher difficulty means more points.\n"
        "10. **/leaderboard** - Show the leaderboard.\n"
        "11. **/top** - Display the top 20 squadrons currently and their stats.\n"
        "12. **/console** - Manage the metalist.\n"
        "13. **/viewmeta** - View the metalist.\n"
        "14. **/time** - Get the current UTC time and your local time.\n"
        "15. **/set-squadron {short hand} {long hand}** - Store squadron name for the discord server (used for logging).\n"
        "16. **/help** - Get a guide on how to use the bot.\n\n"
        "*For detailed information on each command, please read the input descriptions of each command, or reach out to not_so_toothless.*"
    )

    embed = discord.Embed(title="Bot Guide",
                          description=guide_text,
                          color=discord.Color.blue())
    embed.set_footer(text="Meow :3")
    await interaction.response.send_message(embed=embed, ephemeral=False)


# Error handler for all commands
@clear.error
@session.error
@quick_log.error
@win.error
@loss.error
@end.error
@edit.error
async def command_error(interaction: discord.Interaction,
                        error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}",
                                                ephemeral=True)


bot.run(TOKEN)
