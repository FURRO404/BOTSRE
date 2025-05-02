#Alarms.py
import asyncio
import json

import discord
from replit.object_storage import Client

from SQ_Info import fetch_squadron_info

client = Client()
# Function to take a snapshot of the members and their scores
async def take_snapshot(squadron_name):
    snapshot = await fetch_squadron_info(squadron_name)
    return snapshot

# Function to save the snapshot using Replit object storage
def save_snapshot(snapshot, guild_id, squadron_name, region=None):
    if region:
        key = f"SNAPSHOTS/{guild_id}-{squadron_name}-{region}-snapshot"
    else:
        key = f"SNAPSHOTS/{guild_id}-{squadron_name}-snapshot"
    client.upload_from_text(key, json.dumps(snapshot.to_dict()))
    print(f"Snapshot saved for {squadron_name} in guild {guild_id} under {region or 'default'} region")


# Function to load the snapshot using Replit object storage
def load_snapshot(guild_id, squadron_name, region=None):
    if region:
        key = f"SNAPSHOTS/{guild_id}-{squadron_name}-{region}-snapshot"
    else:
        key = f"SNAPSHOTS/{guild_id}-{squadron_name}-snapshot"
    try:
        snapshot_dict = json.loads(client.download_as_text(key))
        return discord.Embed.from_dict(snapshot_dict)
    except Exception as e:
        print(f"Error loading snapshot for {squadron_name} in guild {guild_id} under {region or 'default'} region: {e}")
        return None


def compare_snapshots(old_snapshot, new_snapshot):
    old_members = {}
    new_members = {}
    old_total_members = 0
    new_total_members = 0

    for field in old_snapshot.fields:
        if field.name == "Total Members":
            try:
                old_total_members = int(field.value)
            except ValueError as e:
                print(f"Error parsing old members: {field.value}, error: {e}")

    for field in new_snapshot.fields:
        if field.name == "Total Members":
            try:
                new_total_members = int(field.value)
            except ValueError as e:
                print(f"Error parsing new members: {field.value}, error: {e}")
    
    # Extract old members
    for field in old_snapshot.fields:
        if field.name == "\u00a0":
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    old_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing old snapshot field: {value}, error: {e}")

    # Extract new members
    for field in new_snapshot.fields:
        if field.name == "\u00a0":
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    new_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing new snapshot field: {value}, error: {e}")

    
    if not new_members:
        return {}, {}


    left_members = {}
    name_changes = {}

    # Create a reverse lookup for new members' points -> name
    points_to_name = {points: name for name, points in new_members.items()}

    for member, points in old_members.items():
        if member not in new_members:
            if points not in points_to_name:    
                left_members[member] = points
            else:
                new_name = points_to_name[points]  # Get the new name based on matching points
                name_changes[member] = (new_name)  # Store old name -> new name

    return left_members, name_changes




def compare_points(old_snapshot, new_snapshot):
    old_members = {}
    new_members = {}
    old_total_points = 0

    # Extract old total points & members' points
    for field in old_snapshot.fields:
        if field.name == "Total Points":
            try:
                old_total_points = int(field.value)
            except ValueError as e:
                print(f"Error parsing total points: {field.value}, error: {e}")

        if field.name == "\u00a0":  # Member points data
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    old_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing old snapshot field: {value}, error: {e}")

    # Extract new members' points
    for field in new_snapshot.fields:
        if field.name == "\u00a0":
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    new_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing new snapshot field: {value}, error: {e}")

    # Compare old and new points to detect changes
    points_changes = {}

    # Check existing members
    for member, old_points in old_members.items():
        new_points = new_members.get(member, 0)  # If player left, set their points to zero
        if new_points != old_points:
            points_changes[member] = (new_points - old_points, new_points)

    # Check new members not in old_members
    for member, new_points in new_members.items():
        if member not in old_members:  # New player
            if new_points != 0: #Only include them if they made points
                points_changes[member] = (new_points, new_points)

    return points_changes, old_total_points



async def main():
    embed = await take_snapshot("IC0N")
    print(json.dumps(embed.to_dict(), indent=4))

#asyncio.run(main())