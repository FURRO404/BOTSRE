import asyncio
import json
import logging

import aiohttp

logging.basicConfig(level=logging.INFO)

cache = None

async def fetch_clan_leaderboard(page=1):
    url = f"https://warthunder.com/en/community/getclansleaderboard/dif/_hist/page/{page}/sort/dr_era5"
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        if response.status == 200:
            text = await response.text()  
            try:
                data = json.loads(text)  
                return parse_clan_data(data)
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {e}")
                return None
        else:
            #print(f"Failed to fetch page {page}: HTTP {response.status}")
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
        

async def search_for_clan(short_name, second_iter=False):
    global cache
    """Search for a clan by short_name across up to 1000 pages concurrently.
    Caches data to prevent multiple calls to the API. If the clan is not found on the first iteration, it will refresh the cache and try again.
    If it is not found in the second iteration, it will return None.
    """
    
    if cache is None:
        cache = await get_all_clans()

    for _page, clan_data in enumerate(cache, start=1):
        if clan_data:
            for clan in clan_data:
                if clan["short_name"] == short_name.lower():
                    logging.info(f"{short_name} was found in cache")
                    return clan

    # Condition where it didn't find the clan; refresh cache and try once more
    if not second_iter:
        cache = await get_all_clans()
        logging.warning(f"{short_name} was not found in cache, retrying")
        return await search_for_clan(short_name, second_iter=True)

    if second_iter:
        logging.error(f"{short_name} was not found after both attempts")
        return None  # Clan not found after second iteration


async def get_all_clans():
    """Get all clans from all pages concurrently."""
    max_pages = 1000

    tasks = [fetch_clan_leaderboard(page) for page in range(1, max_pages + 1)]
    results = await asyncio.gather(*tasks)

    return results
    
if __name__ == "__main__":
    result = asyncio.run(search_for_clan("TKBeS"))
    if result:
        print("Clan found:", result)
    else:
        print("Clan not found.")
        