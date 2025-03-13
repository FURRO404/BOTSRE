import asyncio
import aiohttp
import json

async def fetch_clan_leaderboard(page=1):
    url = f"https://warthunder.com/en/community/getclansleaderboard/dif/_hist/page/{page}/sort/dr_era5"
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
    clan_data = await fetch_clan_leaderboard()
    if clan_data:
        return clan_data

async def search_for_clan(short_name):
    """Search for a clan by short_name across up to 500 pages concurrently."""
    max_pages = 500
    
    tasks = [fetch_clan_leaderboard(page) for page in range(1, max_pages + 1)]
    results = await asyncio.gather(*tasks)

    for page, clan_data in enumerate(results, start=1):
        if clan_data:
            for clan in clan_data:
                if clan["short_name"] == short_name.lower():
                    #print(f"Found on page {page}: {clan}")
                    return clan
    return None
    
if __name__ == "__main__":
    result = asyncio.run(search_for_clan("TKBeS"))
    if result:
        print("Clan found:", result)
    else:
        print("Clan not found.")