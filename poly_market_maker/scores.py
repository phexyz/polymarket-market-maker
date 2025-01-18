from poly_market_maker.types import ScoreBoard
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    WebDriverException,
)
from time import sleep


class ScoreFeed:
    def __init__(
        self,
        game_id,
        poll_interval=0.1,
    ):
        self.game_id = game_id
        self.poll_interval = poll_interval
        self.driver = None
        self.wait = None
        self.initialize_driver()

    def initialize_driver(self, max_attempts=3):
        """Initialize the Chrome WebDriver with retry logic"""
        attempt = 0
        while attempt < max_attempts:
            try:
                if self.driver:
                    self.driver.quit()  # Clean up any existing driver

                self.driver = webdriver.Chrome()
                self.driver.get(
                    f"https://www.espn.com/nba/game/_/gameId/{self.game_id}"
                )

                self.wait = WebDriverWait(
                    self.driver,
                    timeout=10,
                    poll_frequency=self.poll_interval,
                    ignored_exceptions=(StaleElementReferenceException,),
                )
                return
            except WebDriverException as e:
                attempt += 1
                if attempt == max_attempts:
                    raise Exception(
                        f"Failed to initialize WebDriver after {max_attempts} attempts: {str(e)}"
                    )
                sleep(2)  # Wait before retrying

    def get_scoreboard(self) -> ScoreBoard:
        """Get current scores using WebDriverWait and parse them"""
        try:
            # If driver seems disconnected, try to reinitialize
            if not self.driver:
                self.initialize_driver()

            # Wait for score elements to be present
            score_elements = self.wait.until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "Gamestrip__Score"))
            )

            time_element = self.wait.until(
                EC.presence_of_element_located(
                    (
                        By.CLASS_NAME,
                        "ScoreCell__Time.Gamestrip__Time",
                    )
                )
            ).text.strip()

            if len(score_elements) >= 2:
                away_score = int(score_elements[0].text.strip())
                home_score = int(score_elements[1].text.strip())

                return ScoreBoard(
                    away_score=away_score, home_score=home_score, game_time=time_element
                )
            return None

        except (TimeoutException, WebDriverException) as e:
            # If we get a connection error, try to reinitialize the driver
            self.initialize_driver()
            return None

    def __del__(self):
        """Cleanup method to ensure driver is closed"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
