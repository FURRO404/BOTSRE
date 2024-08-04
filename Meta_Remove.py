from replit.object_storage import Client
import Searcher
import json
import logging
import requests

client = Client()

def get_metas_key(server_id):
    return f"{server_id}_METAS.txt"

def remove_from_metas(vehicle_name, br, server_id):
    key = get_metas_key(server_id)

    logging.debug(f"Removing vehicle '{vehicle_name}' from BR '{br}' in server '{server_id}'")

    normalized_vehicle_name = Searcher.normalize_name(vehicle_name)
    logging.debug(f"Normalized vehicle name: '{normalized_vehicle_name}'")

    try:
        data = client.download_as_text(key)
        metas = json.loads(data)
        logging.debug(f"Loaded meta data for server {server_id}: {metas}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.debug(f"Meta file for server {server_id} not found.")
            return f"Vehicle {vehicle_name} is not in Meta under BR {br}."
        else:
            logging.error(f"Error loading meta data for server {server_id}: {e}")
            raise
    except Exception as e:
        logging.error(f"Error loading meta data for server {server_id}: {e}")
        return f"An error occurred while trying to remove {vehicle_name} from BR {br}."

    br = br.strip()
    logging.debug(f"Checking for vehicle in BR '{br}'")

    if br not in metas:
        logging.debug(f"BR '{br}' not found in meta data.")
        return f"Vehicle {vehicle_name} is not in Meta under BR {br}."

    normalized_meta_vehicles = [Searcher.normalize_name(vehicle) for vehicle in metas[br]]
    logging.debug(f"Normalized vehicles in BR '{br}': {normalized_meta_vehicles}")

    if normalized_vehicle_name not in normalized_meta_vehicles:
        logging.debug(f"Vehicle '{vehicle_name}' not found in BR '{br}'")
        return f"Vehicle {vehicle_name} is not in Meta under BR {br}."

    metas[br] = [vehicle for vehicle in metas[br] if Searcher.normalize_name(vehicle) != normalized_vehicle_name]
    logging.debug(f"Updated vehicles in BR '{br}': {metas[br]}")

    if not metas[br]:  # Remove BR entry if no vehicles left
        logging.debug(f"No vehicles left in BR '{br}', removing BR entry.")
        del metas[br]

    client.upload_from_text(key, json.dumps(metas))
    logging.debug(f"Meta data successfully updated for server {server_id}")
    return f"Vehicle {vehicle_name} removed from BR {br} in Meta."

def find_vehicles_in_meta(vehicle_name, server_id):
    key = get_metas_key(server_id)

    logging.debug(f"Finding vehicles matching '{vehicle_name}' in server '{server_id}'")

    normalized_vehicle_name = Searcher.normalize_name(vehicle_name).lower()
    logging.debug(f"Normalized search term: '{normalized_vehicle_name}'")

    try:
        data = client.download_as_text(key)
        metas = json.loads(data)
        logging.debug(f"Loaded meta data for server {server_id}: {metas}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.debug(f"Meta file for server {server_id} not found.")
            return {}
        else:
            logging.error(f"Error loading meta data for server {server_id}: {e}")
            raise
    except Exception as e:
        logging.error(f"Error loading meta data for server {server_id}: {e}")
        return {}

    matches = {}
    for br, vehicles in metas.items():
        for vehicle in vehicles:
            if normalized_vehicle_name in Searcher.normalize_name(vehicle).lower():
                if vehicle not in matches:
                    matches[vehicle] = []
                matches[vehicle].append(br)
    logging.debug(f"Found matches: {matches}")
    return matches


# Ensure logging is configured appropriately
logging.basicConfig(level=logging.DEBUG)
