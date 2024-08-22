import datetime
import discord
from replit.object_storage import Client
import json
import logging
import requests
import asyncio
from SQ_Info import fetch_squadron_info

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
    "log": "",
    "starting_points": 0,
    "current_points": 0
}

class Scoreboard:
    sessions = {}

    @classmethod
    def get_session_key(cls, guild_id, user_id):
        return f"{guild_id}_{user_id}_session.json"

    @classmethod
    def load_session(cls, guild_id, user_id):
        key = cls.get_session_key(guild_id, user_id)
        try:
            logging.debug(f"Attempting to download session data for guild {guild_id} and user {user_id}")
            data = client.download_as_text(key)
            cls.sessions[(guild_id, user_id)] = json.loads(data)
            logging.debug(f"Loaded session data for guild {guild_id} and user {user_id}: {cls.sessions[(guild_id, user_id)]}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logging.debug(f"Session data for guild {guild_id} and user {user_id} not found, initializing new session")
                cls.sessions[(guild_id, user_id)] = SESSION_TEMPLATE.copy()
            else:
                logging.error(f"Error loading session data for guild {guild_id} and user {user_id}: {e}")
                raise
        except Exception as e:
            logging.error(f"Error loading session data for guild {guild_id} and user {user_id}: {e}")
            cls.sessions[(guild_id, user_id)] = SESSION_TEMPLATE.copy()

    @classmethod
    def save_session(cls, guild_id, user_id):
        key = cls.get_session_key(guild_id, user_id)
        data = json.dumps(cls.sessions[(guild_id, user_id)])
        logging.debug(f"Saving session data for guild {guild_id} and user {user_id}: {data}")
        client.upload_from_text(key, data)

    @classmethod
    def get_squadron_points(cls, guild_id):
        try:
            squadron_data = client.download_as_text("SQUADRONS.json")
            squadrons = json.loads(squadron_data)
            squadron_info = squadrons.get(str(guild_id))

            if not squadron_info:
                logging.error(f"No squadron set for guild {guild_id}")
                return 0  # Default to 0 if no squadron is set

            long_hand_name = squadron_info['SQ_LongHandName']

            # Fetch the squadron information using the longhand name
            embed = fetch_squadron_info(long_hand_name, "points")
            if embed is not None:
                # Extract the points from the embed's field
                points_field = embed.fields[0]  # Assuming the first field contains the points
                points_value = points_field.value.replace(',', '')  # Remove commas for large numbers
                return int(points_value)
            else:
                logging.error(f"Could not fetch points for squadron {long_hand_name}")
                return 0  # Default to 0 if points cannot be fetched

        except Exception as e:
            logging.error(f"Error fetching squadron points for guild {guild_id}: {e}")
            return 0  # Default to 0 if an error occurs

    @classmethod
    async def start_session(cls, interaction: discord.Interaction, region: str):
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        cls.load_session(guild_id, user_id)

        session = cls.sessions[(guild_id, user_id)]
        if session["started"]:
            await interaction.response.send_message("You already have an active session.", ephemeral=True)
            return

        # Initialize a new session
        session["started"] = True
        session["user"] = user_id
        session["region"] = region

        # Fetch current points for the squadron if set
        squadron_points = cls.get_squadron_points(guild_id)
        session["starting_points"] = squadron_points
        session["current_points"] = squadron_points

        session["log"] = f"{datetime.datetime.utcnow().strftime('%m/%d')}\n{LOG_HEADER}"
        cls.save_session(guild_id, user_id)

        # Send session start message in the channel
        try:
            session_start_message = f"**{session['region']} SESSION START - <@{session['user']}>**"
            message = await interaction.channel.send(f"{session_start_message}\n```diff\n{session['log']}\n```")
            session["last_message_id"] = message.id
            cls.save_session(guild_id, user_id)
            logging.debug(f"Session started message sent: {session_start_message}")
        except Exception as e:
            logging.error(f"Error sending session start message: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"An error occurred while starting the session: {e}", ephemeral=True)

    @classmethod
    async def log_game(cls, interaction: discord.Interaction, status: str, team_name: str, bombers: int, fighters: int,
                       helis: int, tanks: int, spaa: int, comment: str = ""):
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        cls.load_session(guild_id, user_id)

        session = cls.sessions[(guild_id, user_id)]
        if not session["started"]:
            await interaction.response.send_message("No active session found. Please start a session first.", ephemeral=True)
            return

        # Update session data based on status
        if status == "+":
            session["wins"] += 1
        elif status == "-":
            session["losses"] += 1

        new_game_number = session["wins"] + session["losses"]

        # Log entry without points update
        new_log_entry = cls.format_log_entry(status, session["wins"], session["losses"], new_game_number, team_name, bombers, fighters, helis, tanks, spaa, f"(updating...) {comment}")
        session["log_entries"].append(new_log_entry)
        session["log"] = f"{datetime.datetime.utcnow().strftime('%m/%d')}\n{LOG_HEADER}" + "".join(session["log_entries"])

        # Send initial log message
        try:
            if session["last_message_id"]:
                last_message = await interaction.channel.fetch_message(session["last_message_id"])
                await last_message.delete()

            session_start_message = f"**{session['region']} SESSION START - <@{session['user']}>**"
            message = await interaction.channel.send(f"{session_start_message}\n```diff\n{session['log']}\n```")
            session["last_message_id"] = message.id
            cls.save_session(guild_id, user_id)

            # Respond to the interaction
            await interaction.response.send_message("Game logged, updating points...", ephemeral=True)

        except discord.errors.InteractionResponded:
            logging.error("Interaction has already been responded to")
            await interaction.followup.send("Game logged, updating points...", ephemeral=True)

        # Start background task to update points
        asyncio.create_task(cls.update_points_in_log(guild_id, user_id, interaction.channel, message.id))


    

    @classmethod
    async def update_points_in_log(cls, guild_id, user_id, channel, message_id):
        start_time = datetime.datetime.utcnow()
        max_wait_time = datetime.timedelta(minutes=12)
        points_updated = False

        session = cls.sessions[(guild_id, user_id)]
        previous_points = session["current_points"]

        while datetime.datetime.utcnow() - start_time < max_wait_time:
            session["current_points"] = cls.get_squadron_points(guild_id)
            new_points = session["current_points"]

            if new_points != previous_points:
                points_updated = True
                break
            await asyncio.sleep(30)  # Wait 10 seconds before checking again

        # Only update the last entry in the log
        try:
            if session["log_entries"]:
                last_entry_index = -1  # Get the last entry in the list
                last_entry = session["log_entries"][last_entry_index]

                # Update the last entry with the new points or an error message
                point_difference = new_points - previous_points
                point_diff_text = f"(+{point_difference})" if points_updated else "(ERR)"
                updated_entry = last_entry.replace("(updating...)", point_diff_text)

                # Replace the last entry in the session's log
                session["log_entries"][last_entry_index] = updated_entry
                session["log"] = f"{datetime.datetime.utcnow().strftime('%m/%d')}\n{LOG_HEADER}" + "".join(session["log_entries"])

                # Fetch and edit the original message
                message = await channel.fetch_message(message_id)
                await message.edit(content=f"**{session['region']} SESSION START - <@{session['user']}>**\n```diff\n{session['log']}\n```")
                cls.save_session(guild_id, user_id)

        except Exception as e:
            logging.error(f"Error updating points in log: {e}")


    @classmethod
    async def log_win(cls, interaction: discord.Interaction, team_name: str, bombers: int, fighters: int,
                      helis: int, tanks: int, spaa: int, comment: str = ""):
        # Pass "+" for a win status
        await cls.log_game(interaction, "+", team_name, bombers, fighters, helis, tanks, spaa, comment)

    @classmethod
    async def log_loss(cls, interaction: discord.Interaction, team_name: str, bombers: int, fighters: int,
                       helis: int, tanks: int, spaa: int, comment: str = ""):
        # Pass "-" for a loss status
        await cls.log_game(interaction, "-", team_name, bombers, fighters, helis, tanks, spaa, comment)



    @classmethod
    async def end_session(cls, interaction: discord.Interaction, bot: discord.Client):
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        session_key = cls.get_session_key(guild_id, user_id)

        try:
            logging.debug(f"Checking for session file: {session_key}")
            # Attempt to download the session data
            try:
                data = client.download_as_text(session_key)
                session = json.loads(data)
                logging.debug(f"Loaded session data: {session}")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    logging.warning(f"No active session file found for {session_key}")
                    await interaction.response.send_message("No active session found to end.", ephemeral=True)
                    return
                else:
                    raise

            # Calculate win rate
            total_games = session["wins"] + session["losses"]
            win_rate = (session["wins"] / total_games) * 100 if total_games > 0 else 0

            # Fetch final points
            final_points = cls.get_squadron_points(guild_id)

            # Finalize the session log
            session["log"] += f"\n--------------------------\nCALLED - WR: {win_rate:.2f}%\nPOINTS: {session['starting_points']} -> {final_points}\n"
            session_start_message = f"**{session['region']} SESSION START - <@{session['user']}>**"

            # Delete the previous session message
            if session["last_message_id"]:
                try:
                    logging.debug(f"Attempting to delete last session message for guild {guild_id} and user {user_id}")
                    last_message = await interaction.channel.fetch_message(session["last_message_id"])
                    await last_message.delete()
                except discord.errors.NotFound:
                    logging.warning(f"Last message for guild {guild_id} and user {user_id} not found, it might have already been deleted.")
                except Exception as e:
                    logging.error(f"Error deleting last message for guild {guild_id} and user {user_id}: {e}")

            # Send the final session log
            try:
                message = await interaction.channel.send(f"{session_start_message}\n```diff\n{session['log']}\n```")
            except discord.errors.HTTPException as e:
                logging.error(f"Error sending session end message in guild {guild_id}: {e}")
                if not interaction.response.is_done():
                    await interaction.followup.send(f"An error occurred while ending the session: {e}", ephemeral=True)
                return

            # Update the last message ID with the new message
            session["last_message_id"] = message.id

            # Delete the session file
            try:
                client.delete(session_key)
                logging.debug(f"Deleted session file: {session_key}")
            except Exception as e:
                logging.error(f"Error deleting session file {session_key}: {e}")

            if not interaction.response.is_done():
                await interaction.response.send_message("Session ended and file deleted.", ephemeral=True)

        except Exception as e:
            logging.error(f"Unhandled exception while ending session for {session_key}: {e}")
            if not interaction.response.is_done():
                await interaction.followup.send(f"An error occurred while ending the session: {e}", ephemeral=True)

    @classmethod
    async def edit_game(cls, interaction: discord.Interaction, status: str, team_name: str, bombers: int,
                        fighters: int, helis: int, tanks: int, spaa: int, comment: str = ""):
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        cls.load_session(guild_id, user_id)

        session = cls.sessions.get((guild_id, user_id))
        if session is None or not session["started"] or interaction.user.id != session["user"]:
            await interaction.response.send_message("You are not authorized to edit a game or no session is active.", ephemeral=True)
            return

        # Ensure that there are log entries to edit
        if not session["log_entries"]:
            await interaction.response.send_message("No games have been logged yet.", ephemeral=True)
            return

        # Edit the last game entry
        try:
            last_game_index = len(session["log_entries"]) - 1
            last_game_entry = session["log_entries"][last_game_index]

            # Determine the old status and adjust win/loss counts accordingly
            old_status = last_game_entry[0]  # '+' for win, '-' for loss
            new_status = '+' if status.upper() == 'W' else '-'

            if new_status != old_status:
                if new_status == '+':
                    session["wins"] += 1
                    session["losses"] -= 1
                elif new_status == '-':
                    session["wins"] -= 1
                    session["losses"] += 1

            # Recalculate points and log the point difference
            previous_points = session["current_points"]
            session["current_points"] = cls.get_squadron_points(guild_id)
            point_difference = session["current_points"] - previous_points
            point_diff_text = f"(+{point_difference})" if point_difference > 0 else f"({point_difference})"

            # Create the new log entry
            new_game_number = session["wins"] + session["losses"]
            new_log_entry = cls.format_log_entry(new_status, session["wins"], session["losses"], new_game_number, team_name, bombers, fighters, helis, tanks, spaa, f"{point_diff_text} {comment}")
            session["log_entries"][last_game_index] = new_log_entry

            # Rebuild the log
            session["log"] = f"{datetime.datetime.utcnow().strftime('%m/%d')}\n{LOG_HEADER}" + "".join(session["log_entries"])

            # Delete the previous session message and send the updated log
            if session["last_message_id"]:
                last_message = await interaction.channel.fetch_message(session["last_message_id"])
                await last_message.delete()

            session_start_message = f"**{session['region']} SESSION START - <@{session['user']}>**"
            message = await interaction.channel.send(f"{session_start_message}\n```diff\n{session['log']}\n```")
            session["last_message_id"] = message.id

            cls.save_session(guild_id, user_id)

            await interaction.response.send_message("Last game edited.", ephemeral=True)

        except Exception as e:
            logging.error(f"Error editing game: {e}")
            if not interaction.response.is_done():
                await interaction.followup.send(f"An error occurred while editing the game: {e}", ephemeral=True)

    @classmethod
    def format_log_entry(cls, status, wins, losses, game_number, team_name, bombers, fighters, helis, tanks, spaa, comment=''):
        spacing = "   " if len(str(wins)) == 1 and len(str(losses)) == 1 else "  " if len(str(wins)) > 1 and len(str(losses)) == 1 else "  " if len(str(wins)) == 1 and len(str(losses)) > 1 else " "
        return f"{status}{wins}-{losses}{spacing}#{game_number:<2} {team_name:<5} {bombers} {fighters} {helis} {tanks} {spaa} {comment}\n"
