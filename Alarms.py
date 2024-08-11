import json
import discord
from replit.object_storage import Client
from SQ_Info import fetch_squadron_info

client = Client()
# Function to take a snapshot of the members and their scores
def take_snapshot(squadron_name):
    snapshot = fetch_squadron_info(squadron_name, embed_type="members")
    return snapshot

# Function to save the snapshot using Replit object storage
def save_snapshot(snapshot, guild_id, squadron_name):
    key = f"{guild_id}-{squadron_name}-snapshot"
    client.upload_from_text(key, json.dumps(snapshot.to_dict()))
    print(f"Snapshot saved for {squadron_name} in guild {guild_id}")

# Function to load the snapshot using Replit object storage
def load_snapshot(guild_id, squadron_name):
    key = f"{guild_id}-{squadron_name}-snapshot"
    try:
        snapshot_dict = json.loads(client.download_as_text(key))
        return discord.Embed.from_dict(snapshot_dict)
    except Exception as e:
        print(f"Error loading snapshot for {squadron_name} in guild {guild_id}: {e}")
        return None

def compare_snapshots(old_snapshot, new_snapshot):
    old_members = {}
    new_members = {}

    # Extract old members
    for field in old_snapshot.fields:
        if field.name == "\u00A0":
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
        if field.name == "\u00A0":
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    new_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing new snapshot field: {value}, error: {e}")

    print(f"Old members: {old_members}")
    print(f"New members: {new_members}")

    left_members = {}
    for member, points in old_members.items():
        if member not in new_members and points > 0:
            left_members[member] = points

    return left_members


