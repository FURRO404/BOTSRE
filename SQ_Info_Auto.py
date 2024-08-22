from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import requests
from bs4 import BeautifulSoup

def fetch_clan_table_info(sq_name):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service("/nix/store/n4qcnqy0isnvxcpcgv6i2z9ql9wsxksw-chromedriver-114.0.5735.90/bin/chromedriver"), options=chrome_options)

    try:
        page_number = 1
        while True:
            url = f"https://warthunder.com/en/community/clansleaderboard/page/{page_number}/"
            driver.get(url)

            wait = WebDriverWait(driver, 30)
            table = wait.until(EC.presence_of_element_located((By.XPATH, '//table')))

            rows = wait.until(EC.presence_of_all_elements_located((By.XPATH, '//table//tr')))
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, 'td')
                row_data = [cell.text for cell in cells]  # Capture all cell contents for each row
                if len(cells) > 1 and sq_name in cells[1].text:
                    return row_data  # Return the full line as a list

            # Check if there's a next page or if we've reached the last page
            next_button = driver.find_elements(By.XPATH, "//a[contains(@class, 'next')]")
            if not next_button:
                break  # No more pages to check

            page_number += 1

    except TimeoutException:
        return "Timeout occurred while trying to find the clan"

    finally:
        driver.quit()

    return "Clan not found"

def fetch_first_page_clan_table():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service("/nix/store/n4qcnqy0isnvxcpcgv6i2z9ql9wsxksw-chromedriver-114.0.5735.90/bin/chromedriver"), options=chrome_options)

    try:
        url = "https://warthunder.com/en/community/clansleaderboard/page/1/"
        driver.get(url)

        wait = WebDriverWait(driver, 30)
        table = wait.until(EC.presence_of_element_located((By.XPATH, '//table')))

        rows = wait.until(EC.presence_of_all_elements_located((By.XPATH, '//table//tr')))
        first_page_data = []
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, 'td')
            row_data = [cell.text for cell in cells]  # Capture all cell contents for each row
            if len(cells) > 1:  # Ensure that the row contains relevant data
                first_page_data.append(row_data)

        return first_page_data  # Return the full content of the first page as a list of lists

    except TimeoutException:
        return "Timeout occurred while trying to fetch the first page"

    finally:
        driver.quit()



# Function to fetch and parse the clan info page for a given squadron
def process_sq(squadron_full_name):
    baseURL = 'https://warthunder.com/en/community/claninfo/'
    team_url = f"{baseURL}{squadron_full_name}"

    response = requests.get(team_url)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')

        stat_values = []
        playtime = 'N/A'
        for item in soup.select('ul.squadrons-stat__item li.squadrons-stat__item-value'):
            text = item.text.strip()
            try:
                stat_values.append(int(text))
            except ValueError:
                if "d" in text:
                    playtime = text

        if len(stat_values) >= 3:
            air_kills = stat_values[0]
            ground_kills = stat_values[1]
            deaths = stat_values[2]

            squadron_score_div = soup.find('div', class_='squadrons-counter__value')
            squadron_score = int(squadron_score_div.text.strip()) if squadron_score_div else 'N/A'

            kd_ratio = round((air_kills + ground_kills) / deaths, 2) if deaths > 0 else 'N/A'

            return {
                'Squadron Name': squadron_full_name,
                'Squadron Score': squadron_score,
                'Air Kills': air_kills,
                'Ground Kills': ground_kills,
                'Deaths': deaths,
                'KD Ratio': kd_ratio,
                'Playtime': playtime
            }
        else:
            print(f"Not enough valid stats found for {squadron_full_name}.")
    else:
        print(f"Failed to fetch clan info page for {squadron_full_name}. Status code: {response.status_code}")

    return None

# Main function to process all 20 squadrons
def process_all_squadrons():
    # Fetch the first page of the leaderboard
    leaderboard_data = fetch_first_page_clan_table()

    all_squadron_stats = []

    if leaderboard_data and len(leaderboard_data) > 0:
        # Extract and process each squadron's stats
        for team in leaderboard_data:
            if isinstance(team, list):
                squadron_full_name = ' '.join(team[1].split()[1:])  # Extract the full name (everything after the short name)
                squadron_stats = process_sq(squadron_full_name)
                if squadron_stats:
                    all_squadron_stats.append(squadron_stats)
    else:
        print("No data found on the first page of the leaderboard.")

    return all_squadron_stats if all_squadron_stats else None
