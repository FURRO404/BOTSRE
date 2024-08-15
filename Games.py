import random
import os
import re
import requests
from bs4 import BeautifulSoup
from Searcher import get_vehicle_country
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def normalize_name(name):
    return re.sub(r'[^\w\s\(\)\-/.]', '', name).strip()

def get_random_vehicle_file():
    files = ["Air.txt", "Ground.txt", "Naval.txt"]
    selected_file = random.choice(files)
    logging.debug(f"Selected file: {selected_file}")
    return os.path.join(os.path.dirname(__file__), "DATA", selected_file)

def choose_random_vehicle(file_path):
    logging.debug(f"Choosing random vehicle from file: {file_path}")
    try:
        with open(file_path, "r", encoding='utf-8') as file:
            lines = file.readlines()

        vehicles = []
        i = 0
        while i < len(lines):
            if not lines[i].startswith('\t') and lines[i].strip() != "":
                if i + 1 < len(lines) and not lines[i + 1].startswith('\t'):
                    vehicle_name = lines[i + 1].strip()
                    normalized_name = normalize_name(vehicle_name)
                    if i + 2 < len(lines):
                        numbers_line = lines[i + 2]
                        numbers = numbers_line.split()
                        if len(numbers) == 3:
                            br = numbers[1]
                            vehicles.append((vehicle_name, normalized_name, br))
                i += 3
            else:
                i += 1

        if vehicles:
            logging.debug(f"Total vehicles found: {len(vehicles)}")
            return vehicles
        else:
            logging.warning("No vehicles found in the file.")
            return []
    except Exception as e:
        logging.error(f"Error in choose_random_vehicle function: {e}")
        return []

def fetch_garage_image_url(normalized_name):
    logging.debug(f"Fetching garage image URL for: {normalized_name}")
    try:
        url = f"https://wiki.warthunder.com/{normalized_name.replace(' ', '_')}"
        logging.debug(f"Constructed URL: {url}")
        response = requests.get(url)
        response.raise_for_status()  # Check if the request was successful
        response_text = response.text

        # Parse the HTML with BeautifulSoup
        soup = BeautifulSoup(response_text, 'html.parser')

        # Find all image elements
        image_elements = soup.find_all('img')

        # Extract the URL of the garage image
        garage_image_url = None
        for image_element in image_elements:
            if 'src' in image_element.attrs and 'GarageImage_' in image_element['src']:
                garage_image_url = image_element['src']
                if not garage_image_url.startswith('http'):
                    garage_image_url = 'https://wiki.warthunder.com' + garage_image_url
                break

        # Print and return the garage image URL
        if garage_image_url:
            logging.debug(f"Found garage image URL: {garage_image_url}")
        else:
            logging.warning("Garage image not found.")

        return garage_image_url

    except Exception as e:
        logging.error(f"Error fetching garage image URL: {e}")
        return None

def guessing_game():
    logging.debug("Starting guessing game")
    file_path = get_random_vehicle_file()
    vehicles = choose_random_vehicle(file_path)

    if not vehicles:
        logging.warning("No vehicles found.")
        return "No vehicles found.", None, None

    random.shuffle(vehicles)  # Shuffle the list to try different vehicles
    for selected_vehicle, normalized_name, selected_br in vehicles:
        image_url = fetch_garage_image_url(normalized_name)
        if image_url:
            logging.debug(f"Game setup complete with vehicle: {selected_vehicle}, image URL: {image_url}")
            return selected_vehicle, normalized_name, image_url

    logging.warning("No images found.")
    return "No images found.", None, None


def get_country_flag(country):
    flags = {
        "USSR": "🇷🇺",
        "Germany": "🇩🇪",
        "USA": "🇺🇸",
        "Great Britain": "🇬🇧",
        "Japan": "🇯🇵",
        "Italy": "🇮🇹",
        "France": "🇫🇷",
        "China": "🇨🇳",
        "Sweden": "🇸🇪",
        "Israel": "🇮🇱"
    }
    return flags.get(country, "")

def randomizer_game():
    logging.debug("Choosing random stuff")
    file_path = get_random_vehicle_file()
    vehicles = choose_random_vehicle(file_path)
    random.shuffle(vehicles)

    if vehicles:
        # Choose a random vehicle
        selected_vehicle, normalized_name, selected_br = vehicles[0]

        # Get the country of the vehicle
        vehicle_country = get_vehicle_country(normalized_name)
        country_flag = get_country_flag(vehicle_country)

        # Print the chosen vehicle details with the flag
        return (f"Chosen vehicle: **{normalized_name}** ({country_flag}) @ BR: **{selected_br}**.\nGood luck!")
    else:
        return ("No vehicles available for selection.")

