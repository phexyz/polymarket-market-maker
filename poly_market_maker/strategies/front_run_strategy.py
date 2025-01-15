from selenium import webdriver
from selenium.webdriver.common.by import By
import time

# Initialize the WebDriver
driver = webdriver.Chrome()

# Open the target webpage
driver.get("https://www.espn.com/nba/game/_/gameId/401705116")

try:
    while True:
        # Find all elements with class "Gamestrip__Score"
        scores = driver.find_elements(By.CLASS_NAME, "Gamestrip__Score")

        # Print the text content of each score
        for idx, score in enumerate(scores):
            print(f"Score {idx + 1}: {score.text}")

        # Wait 0.5 seconds before the next iteration
        time.sleep(0.5)
except KeyboardInterrupt:
    print("Stopping the loop.")
finally:
    driver.quit()
