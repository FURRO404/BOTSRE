from replit.object_storage import Client
import json
import logging
import requests

client = Client()


def get_permissions_key(server_id):
    return f"{server_id}_permissions.json"


def load_permissions(server_id):
    key = get_permissions_key(server_id)
    try:
        data = client.download_as_text(key)
        return json.loads(data)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.debug(
                f"Permissions file for guild {server_id} not found, creating a new one"
            )
            return {}
        else:
            logging.error(
                f"Error loading permissions data for server {server_id}: {e}")
            raise
    except Exception as e:
        logging.error(
            f"Error loading permissions data for server {server_id}: {e}")
        return {}


def save_permissions(server_id, permissions):
    key = get_permissions_key(server_id)
    data = json.dumps(permissions)
    logging.debug(f"Saving permissions data for guild {server_id}: {data}")
    try:
        client.upload_from_text(key, data)
    except Exception as e:
        logging.error(
            f"Error saving permissions data for server {server_id}: {e}")


def grant_permission(target_id, permission_type, server_id, is_role):
    permissions = load_permissions(server_id)
    if permission_type not in permissions:
        permissions[permission_type] = {'roles': [], 'users': []}

    target_list = permissions[permission_type][
        'roles'] if is_role else permissions[permission_type]['users']
    if target_id not in target_list:
        target_list.append(target_id)
        save_permissions(server_id, permissions)


def revoke_permission(target_id, permission_type, server_id, is_role):
    permissions = load_permissions(server_id)
    if permission_type not in permissions:
        return

    target_list = permissions[permission_type][
        'roles'] if is_role else permissions[permission_type]['users']
    if target_id in target_list:
        target_list.remove(target_id)
        save_permissions(server_id, permissions)


def has_permission(user_id, roles, permission_type, server_id):
    permissions = load_permissions(server_id)
    if permission_type not in permissions:
        return False

    if user_id in permissions[permission_type]['users']:
        return True

    user_role_ids = [role.id for role in roles]
    if any(role_id in permissions[permission_type]['roles']
           for role_id in user_role_ids):
        return True

    return False
