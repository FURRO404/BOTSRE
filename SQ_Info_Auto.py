from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException




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

