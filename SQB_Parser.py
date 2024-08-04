import re
import json

class EventCasualty:
    def __init__(self, actor, target):
        self.actor = actor
        self.target = target

class EventFatality:
    def __init__(self, actor, target):
        self.actor = actor
        self.target = target

class EventDiedSolo:
    def __init__(self, actor):
        self.actor = actor

class EventSolo:
    def __init__(self, actor):
        self.actor = actor

class EventEmpty:
    pass

def extract_name(text):
    match = re.search(r"^[^()]+", text)
    return match.group(0).strip() if match else None

def extract_vehicle(text):
    match = re.search(r"(\([^()]+(?:[()]?[^()]+)*\))", text)
    return match.group(1) if match else None

class EventType:
    def __init__(self, needle, test_func, parser_func):
        self.needle = needle
        self.test = test_func
        self.parser = parser_func

def create_event_type(needle, parser_func):
    def test_func(text):
        return re.search(needle, text) and not re.search(r'[(]Recon Micro[)]', text, re.IGNORECASE) and not re.search(r'Recon Micr', text, re.IGNORECASE)
    return EventType(needle, test_func, parser_func)

event_types = {
    'damaged': create_event_type(r' damaged ', lambda text: EventCasualty(
        {'name': extract_name(text.split(' damaged ')[0]), 'vehicle': extract_vehicle(text.split(' damaged ')[0])},
        {'name': extract_name(text.split(' damaged ')[1]), 'vehicle': extract_vehicle(text.split(' damaged ')[1])}
    )),
    'destroyed': create_event_type(r' destroyed ', lambda text: EventFatality(
        {'name': extract_name(text.split(' destroyed ')[0]), 'vehicle': extract_vehicle(text.split(' destroyed ')[0])},
        {'name': extract_name(text.split(' destroyed ')[1]), 'vehicle': extract_vehicle(text.split(' destroyed ')[1])}
    )),
    'fire': create_event_type(r' set afire ', lambda text: EventCasualty(
        {'name': extract_name(text.split(' set afire ')[0]), 'vehicle': extract_vehicle(text.split(' set afire ')[0])},
        {'name': extract_name(text.split(' set afire ')[1]), 'vehicle': extract_vehicle(text.split(' set afire ')[1])}
    )),
    'downed': create_event_type(r' shot down ', lambda text: EventFatality(
        {'name': extract_name(text.split(' shot down ')[0]), 'vehicle': extract_vehicle(text.split(' shot down ')[0])},
        {'name': extract_name(text.split(' shot down ')[1]), 'vehicle': extract_vehicle(text.split(' shot down ')[1])}
    )),
    'disconnect': EventType(r' kd[?]NET_PLAYER_DISCONNECT_FROM_GAME', lambda text: re.search(r' kd[?]NET_PLAYER_DISCONNECT_FROM_GAME', text),
        lambda text: EventDiedSolo({'name': extract_name(text.split(r' kd[?]NET_PLAYER_DISCONNECT_FROM_GAME')[0])})
    ),
    'chrashed': EventType(r' has crashed.', lambda text: re.search(r' has crashed.', text),
        lambda text: EventDiedSolo({'name': extract_name(text.split(' has crashed.')[0]), 'vehicle': extract_vehicle(text.split(' has crashed.')[0])})
    ),
    'hasAchieved': EventType(r' has achieved ', lambda text: re.search(r' has achieved ', text),
        lambda text: EventSolo({'name': extract_name(text.split(' has achieved ')[0]), 'vehicle': extract_vehicle(text.split(' has achieved ')[0])})
    ),
    'died': EventType(r' has died.$', lambda text: re.search(r' has died.$', text),
        lambda text: EventDiedSolo({'name': extract_name(text)})
    ),
    'firstStrike': EventType(r' has delivered the first strike!', lambda text: re.search(r' has delivered the first strike!', text),
        lambda text: EventSolo({'name': extract_name(text.split(' has delivered the first strike!')[0]), 'vehicle': extract_vehicle(text.split(' has delivered the first strike!')[0])})
    ),
    'downedDrone': EventType(r'shot down [(]?Recon Micro[)]?$', lambda text: re.search(r'shot down [(]?Recon Micro[)]?$', text),
        lambda text: EventSolo({'name': extract_name(text.split(r'shot down [(]?Recon Micro[)]?$')[0]), 'vehicle': extract_vehicle(text.split(r'shot down [(]?Recon Micro[)]?$')[0])})
    ),
    'damagedDrone': EventType(r'damaged [(]?Recon Micro[)]?$', lambda text: re.search(r'damaged [(]?Recon Micro[)]?$', text),
        lambda text: EventSolo({'name': extract_name(text.split(r'damaged [(]?Recon Micro[)]?$')[0]), 'vehicle': extract_vehicle(text.split(r'damaged [(]?Recon Micro[)]?$')[0])})
    ),
    'unknown': EventType('', lambda text: False, lambda text: EventEmpty())
}

def parse_log(log_entry):
    for event_type in event_types.values():
        if event_type.test(log_entry):
            return event_type.parser(log_entry)
    return event_types['unknown'].parser(log_entry)

def parse_logs(logs, clan_tag):
    parsed_events = []
    clan_members = set()  # Use a set to avoid duplicates
    for log in logs:
        if clan_tag in log['msg']:
            parsed_event = parse_log(log['msg'])
            parsed_events.append(log['msg'])  # Append the original message instead of the event object for display purposes

            # Check if the clan tag is in the actor or target and append the correct member
            if isinstance(parsed_event, EventCasualty) or isinstance(parsed_event, EventFatality):
                if clan_tag in parsed_event.actor['name']:
                    clan_members.add(f"{parsed_event.actor['name']} : {parsed_event.actor['vehicle']}")
                elif clan_tag in parsed_event.target['name']:
                    clan_members.add(f"{parsed_event.target['name']} : {parsed_event.target['vehicle']}")
            elif isinstance(parsed_event, EventSolo) or isinstance(parsed_event, EventDiedSolo):
                if clan_tag in parsed_event.actor['name']:
                    clan_members.add(f"{parsed_event.actor['name']} : {parsed_event.actor.get('vehicle', '')}")

    return parsed_events, clan_members

def separate_games(logs):
    games = []
    current_game = []
    previous_time = float('inf')  # Start with an infinitely large time
    game_change_ids = []  # Track the log IDs where game changes occur

    for log in logs:
        current_time = log['time']
        if current_time > previous_time:  # Indicates the start of a new game
            games.append(current_game)
            current_game = []
            game_change_ids.append(log['id'])  # Add the log ID
        current_game.append(log)
        previous_time = current_time

    if current_game:  # Append the last collected game
        games.append(current_game)

    return games, game_change_ids

def read_logs_from_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        logs_json = file.read()
    logs = json.loads(logs_json)
    return logs

def main():
    clan_tag = input("Enter the clan tag to filter by: ")
    logs = read_logs_from_file('input.txt')
    logs['damage'].reverse()  # Reverse the order of the logs
    games, _ = separate_games(logs['damage'])

    if games:
        print("Processing Game 1:")
        parsed_events, clan_members = parse_logs(games[0], clan_tag)
        for event in parsed_events:
            print(event)
        print("\nClan Members Vehicles:")
        for member in clan_members:
            print(member)
    else:
        print("No games found.")


