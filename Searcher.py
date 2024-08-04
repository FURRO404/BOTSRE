import re
import os
import logging

def normalize_name(name):
    return re.sub(r'[^\w\s\(\)\-/.]', '', name).strip()

def get_BR(vehicle_name, lines):
    logging.debug(f"Searching for vehicle: {vehicle_name}")
    lines = [line.strip() for line in lines]
    normalized_vehicle_name = normalize_name(vehicle_name)
    logging.debug(f"Normalized vehicle name: {normalized_vehicle_name}")

    for i in range(len(lines)):
        normalized_line_name = normalize_name(lines[i])
        if normalized_line_name == normalized_vehicle_name:
            if i + 1 < len(lines):
                numbers_line = lines[i + 1]
                numbers = numbers_line.split()
                if len(numbers) == 3:
                    BR = numbers[1]
                    logging.debug(f"Found BR: {BR} for vehicle: {vehicle_name}")
                    return BR
    return None

def search_vehicle(vehicle_name):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ground_file_path = os.path.join(script_dir, "DATA", "Ground.txt")
        air_file_path = os.path.join(script_dir, "DATA", "Air.txt")

        with open(ground_file_path, "r", encoding='utf-8') as file:
            ground_lines = file.readlines()
        BR = get_BR(vehicle_name, ground_lines)
        if BR:
            return BR

        with open(air_file_path, "r", encoding='utf-8') as file:
            air_lines = file.readlines()
        BR = get_BR(vehicle_name, air_lines)
        if BR:
            return BR
    except Exception as e:
        logging.error(f"Error searching for vehicle: {e}")
        return None

    return None

def search_vehicle_type(vehicle_name, lines):
    normalized_vehicle_name = normalize_name(vehicle_name)
    for i in range(len(lines)):
        if lines[i].startswith('\t'):
            continue
        normalized_line_name = normalize_name(lines[i])
        if normalized_line_name == normalized_vehicle_name:
            if i - 1 >= 0 and not lines[i - 1].startswith('\t'):
                return lines[i - 1].strip()
    return None

def get_vehicle_type(vehicle_name):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ground_file_path = os.path.join(script_dir, "DATA", "Ground.txt")
        air_file_path = os.path.join(script_dir, "DATA", "Air.txt")

        with open(ground_file_path, "r", encoding='utf-8') as file:
            ground_lines = file.readlines()
        vehicle_type = search_vehicle_type(vehicle_name, ground_lines)
        if vehicle_type:
            return vehicle_type

        with open(air_file_path, "r", encoding='utf-8') as file:
            air_lines = file.readlines()
        vehicle_type = search_vehicle_type(vehicle_name, air_lines)
        if vehicle_type:
            return vehicle_type
    except Exception as e:
        logging.error(f"Error getting vehicle type: {e}")
        return None

    return None

def get_vehicle_country(vehicle):
    logging.debug(f"Getting country for vehicle: {vehicle}")

    def search_vehicle_in_file(file_path):
        try:
            with open(file_path, "r", encoding='utf-8') as file:
                lines = file.readlines()

            normalized_vehicle_name = normalize_name(vehicle)
            for i in range(len(lines)):
                normalized_line_name = normalize_name(lines[i])
                if normalized_line_name == normalized_vehicle_name:
                    if i - 1 >= 0 and '\t' in lines[i - 1]:
                        country = lines[i - 1].split('\t')[0]
                        logging.debug(f"Found country '{country}' for vehicle '{vehicle}' in file '{file_path}'")
                        return country
            return None
        except Exception as e:
            logging.error(f"Error in search_vehicle_in_file function: {e}")
            return None

    data_files = ["DATA/Ground.txt", "DATA/Air.txt"]
    for data_file in data_files:
        file_path = os.path.join(os.path.dirname(__file__), data_file)
        country = search_vehicle_in_file(file_path)
        if country:
            return country

    logging.warning(f"Vehicle '{vehicle}' not found in any data files.")
    return None

def autofill_search(vehicle_name):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ground_file_path = os.path.join(script_dir, "DATA", "Ground.txt")
        air_file_path = os.path.join(script_dir, "DATA", "Air.txt")

        with open(ground_file_path, "r", encoding='utf-8') as file:
            ground_lines = file.readlines()
        vehicle_name_autofilled = get_closest_match(vehicle_name, ground_lines)
        if vehicle_name_autofilled:
            return vehicle_name_autofilled

        with open(air_file_path, "r", encoding='utf-8') as file:
            air_lines = file.readlines()
        vehicle_name_autofilled = get_closest_match(vehicle_name, air_lines)
        if vehicle_name_autofilled:
            return vehicle_name_autofilled
    except Exception as e:
        logging.error(f"Error searching for vehicle: {e}")
        return None

    return None

def get_closest_match(vehicle_name, lines):
    normalized_vehicle_name = normalize_name(vehicle_name)
    for line in lines:
        if normalized_vehicle_name in normalize_name(line):
            return line.strip()
    return None
