import re
import json
import requests
import discord
from discord import Embed
from bs4 import BeautifulSoup

# --- PUBLIC VARIABLES (Global) ---
# Target URL
baseURL = 'https://warthunder.com/en/community/claninfo/'

# Forms a complete URL pointing to the appropriate squadron page, then calls the scraper function using said URL.
def getData(squad):
    return scraper(baseURL + squad)

# Scrapes data from the provided URL
def scraper(url):
    try:
        response = requests.get(url, timeout=60)
        content = BeautifulSoup(response.content, "lxml")
        return parser(content)
    except (requests.exceptions.RequestException, Exception) as e:
        print(f"Error raised in 'scraper' function: {e}")
        return None

# Parses the HTML content and returns a structured dictionary
def parser(content):
    players = []
    total_points = 0
    counter = 0

    # Extract total points
    total_points_tag = content.find('div', class_='squadrons-counter__value')
    if total_points_tag:
        total_points = int(total_points_tag.text.strip())

    for dataItem in content.findAll('div', attrs={"class": "squadrons-members__grid-item"}):
        if counter == 7: # Get player name from the link element.
            name = (dataItem.find('a').get('href')).replace('en/community/userinfo/?nick=', '')
        elif counter == 8: # Get player points
            points = re.sub(r'\s+', '', dataItem.text)
        elif counter == 12:
            # Create an object using the previous variables, append it to the playerArray.
            players.append({
                'name': name,
                'points': int(points) if points.isdigit() else 0
            })
            counter = 6
        counter += 1

    return players, total_points

# Generates a summary report
def generate_summary(players, total_points):
    total_members = len(players)
    return {
        'total_points': total_points,
        'total_members': total_members
    }

# Function to create an embed with the player data based on the type
def create_embed(players, summary, squadron_name, embed_type=None):
    embed = discord.Embed(title=f"Squadron Info: {squadron_name}", color=0x00ff00)

    if embed_type == "members":
        players_sorted = sorted(players, key=lambda x: x['points'], reverse=True)
        player_list = [player['name'].replace('_', '\\_') + f": {player['points']} points" for player in players_sorted]
        player_chunks = []
        current_chunk = ""

        for player in player_list:
            if len(current_chunk) + len(player) + 1 > 1024:
                player_chunks.append(current_chunk.strip())
                current_chunk = player + "\n"
            else:
                current_chunk += player + "\n"

        if current_chunk:
            player_chunks.append(current_chunk.strip())  # Add the last chunk

        for chunk in player_chunks:
            embed.add_field(name="\u00A0", value=chunk, inline=False)  # \u00A0 is a non-breaking space

    elif embed_type == "points":
        embed.add_field(name="Total Points", value=summary['total_points'], inline=False)
    else:
        embed.add_field(name="Total Members", value=summary['total_members'], inline=False)
        embed.add_field(name="Total Points", value=summary['total_points'], inline=False)

        players_sorted = sorted(players, key=lambda x: x['points'], reverse=True)
        player_list = [player['name'].replace('_', '\\_') + f": {player['points']} points" for player in players_sorted]
        player_chunks = []
        current_chunk = ""

        for player in player_list:
            if len(current_chunk) + len(player) + 1 > 1024:
                player_chunks.append(current_chunk.strip())
                current_chunk = player + "\n"
            else:
                current_chunk += player + "\n"

        if current_chunk:
            player_chunks.append(current_chunk.strip())  # Add the last chunk

        for chunk in player_chunks:
            embed.add_field(name="\u00A0", value=chunk, inline=False)  # \u00A0 is a non-breaking space

    return embed




# Main function to fetch and format squadron data
def fetch_squadron_info(squadron_name, embed_type=None):
    squad = squadron_name.replace(" ", "%20")
    players, total_points = getData(squad)
    if players is not None:
        summary = generate_summary(players, total_points)
        embed = create_embed(players, summary, squadron_name, embed_type)
        return embed
    else:
        return None
