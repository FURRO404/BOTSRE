from replit.object_storage import Client
import json
import logging
import requests
from Searcher import search_vehicle, get_vehicle_type

client = Client()

def add_to_metas(vehicle_name: str, user_br: str, guild_id: int):
    br = search_vehicle(vehicle_name)
    if br is None:
        return f"Vehicle name '{vehicle_name}' not found in Ground or Air data."

    vehicle_type = get_vehicle_type(vehicle_name)
    if vehicle_type:
        if 'Light tank' in vehicle_type or 'Medium tank' in vehicle_type or 'Heavy tank' in vehicle_type or 'Tank destroyer' in vehicle_type:
            category = 'Ground Forces'
        elif 'SPAA' in vehicle_type:
            category = 'Anti-Aircraft'
        elif 'helicopter' in vehicle_type.lower():
            category = 'Helis'
        else:
            category = 'Air Forces'

        # Unfortunately GRB BR is split for Air in SRE and Air to GRB is not in a wiki
        if category not in ['Air Forces']:
            # Check if the BR from the data files is not higher than the user's provided BR
            try:
                br_value = float(br)
                user_br_value = float(user_br)
                if br_value > user_br_value:
                    message = f"Vehicle '{vehicle_name}' has a BR of {br}, which is higher than the provided BR {user_br}."
                    logging.info(message)
                    return message
            except ValueError:
                return "Invalid BR value provided."
    else:
        return "Vehicle type not determined."

    key = f"{guild_id}_METAS.txt"
    try:
        data = client.download_as_text(key)
        metas = json.loads(data)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.debug(f"Meta file for guild {guild_id} not found, creating a new one.")
            metas = {}
        else:
            logging.error(f"Error loading meta data for guild {guild_id}: {e}")
            raise
    except Exception as e:
        logging.error(f"Error loading meta data for guild {guild_id}: {e}")
        metas = {}

    if user_br not in metas:
        metas[user_br] = []
    if vehicle_name not in metas[user_br]:
        metas[user_br].append(vehicle_name)
        client.upload_from_text(key, json.dumps(metas))
        message = f"{vehicle_name} added to BR {user_br}."
        logging.info(message)
        return message
    else:
        message = f"{vehicle_name} is already present at BR {user_br}."
        logging.info(message)
        return message

# Ensure logging is configured appropriately
logging.basicConfig(level=logging.DEBUG)
