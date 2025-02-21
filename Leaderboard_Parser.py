import asyncio
import aiohttp
import json

async def fetch_clan_leaderboard(page=1):
    url = f"https://warthunder.com/en/community/getclansleaderboard/dif/_hist/page/{page}/sort/tagl"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                text = await response.text()  # Get response as text
                try:
                    data = json.loads(text)  # Manually parse JSON
                    return parse_clan_data(data)
                except json.JSONDecodeError as e:
                    print(f"JSON parsing error: {e}")
                    print("Response text:", text[:500])  # Print first 500 chars for debugging
                    return None
            else:
                print(f"Failed to fetch page {page}: HTTP {response.status}")
                return None

def parse_clan_data(data):
    if data.get("status") != "ok":
        return []

    clans = []
    for entry in data.get("data", []):
        clan_info = {
            "position": entry.get("pos"),
            "long_name": entry.get("name"),
            "short_name": entry.get("tagl"),
            "tag": entry.get("lastPaidTag")[1:-1] if entry.get("lastPaidTag") else None,
            "members": entry.get("members_cnt"),
            "wins": entry.get("astat", {}).get("wins_hist"),
            "battles": entry.get("astat", {}).get("battles_hist"),
            "a_kills": entry.get("astat", {}).get("akills_hist"),
            "g_kills": entry.get("astat", {}).get("gkills_hist"),
            "deaths": entry.get("astat", {}).get("deaths_hist"),
            "playtime": entry.get("astat", {}).get("ftime_hist"),
            "clanrating": entry.get("astat", {}).get("dr_era5_hist"),
        }
        clans.append(clan_info)

    return clans

async def get_top_20():
    page = 1
    clan_data = await fetch_clan_leaderboard(page)
    if clan_data:
        return clan_data

async def search_for_clan(short_name):
    """Search for a squadron by short_name, page by page, up to a maximum of 50 pages."""
    max_pages = 75
    page = 1
    while page <= max_pages:
        clan_data = await fetch_clan_leaderboard(page)
        if not clan_data:
            break
        for clan in clan_data:
            if clan["short_name"] == short_name.lower():
                print(clan)
                return clan
        page += 1
    return None


test = search_for_clan("avr")
#asyncio.run(test)
#asyncio.run(get_top_20())
