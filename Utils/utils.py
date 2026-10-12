import os
import time
import logging

from typing import Optional, Any
from selenium import webdriver
from selenium.webdriver import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.select import Select
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    ElementNotInteractableException, StaleElementReferenceException
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def safe_execute_with_retry(func, max_retries: int = 3, delay: float = 1.0, *args, **kwargs):
    """Execute a function with retry logic and exception handling."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (StaleElementReferenceException, ElementNotInteractableException) as e:
            if attempt < max_retries - 1:
                logger.warning(f"Retrying {func.__name__} (attempt {attempt + 1}): {e}")
                time.sleep(delay)
                continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Retrying {func.__name__} (attempt {attempt + 1}): {e}")
                time.sleep(delay)
                continue
            logger.error(f"Failed {func.__name__} after {max_retries} attempts: {e}")
            raise


def click_element_by_js(driver, by_locator, timeout: int = 10, max_retries: int = 3) -> bool:
    """Click element using JavaScript with exception handling and retry logic."""
    def _js_click():
        try:
            element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(by_locator))
            driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'nearest'})", element)
            time.sleep(0.5)  # Allow scroll to complete
            driver.execute_script("arguments[0].click();", element)
            time.sleep(0.5)
            return True
        except TimeoutException:
            logger.error(f"Element not found for JS click within {timeout} seconds: {by_locator}")
            return False
        except WebDriverException as e:
            logger.error(f"JavaScript execution failed: {e}")
            return False

    try:
        return safe_execute_with_retry(_js_click, max_retries)
    except Exception as e:
        logger.error(f"Critical error in click_element_by_js: {e}")
        return False


def input_element(driver, by_locator, text: str, timeout: int = 10, max_retries: int = 3) -> bool | None | Any:
    """Input text with comprehensive exception handling and validation."""
    def _input_text():
        try:
            element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(by_locator))
            driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center', inline: 'nearest'})", element)
            time.sleep(0.5)

            # Clear the field safely
            element.clear()
            time.sleep(0.2)

            # if not cleared, use backspace to ensure the field is empty
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.BACKSPACE)
            time.sleep(0.2)

            # Input the text
            element.send_keys(text)
            time.sleep(0.3)

            return True
        except TimeoutException:
            logger.error(f"Input element not found within {timeout} seconds: {by_locator}")
            return False
        except (NoSuchElementException, ElementNotInteractableException) as e:
            logger.error(f"Element input failed: {e}")
            return False
        except WebDriverException as e:
            logger.error(f"WebDriver error during input: {e}")
            return False

    try:
        if not text:
            logger.warning("Empty text provided for input")
            return True
        return safe_execute_with_retry(_input_text, max_retries)
    except Exception as e:
        logger.error(f"Critical error in input_element: {e}")
        return False


def move_to_element(driver, locator, timeout: int = 10, max_retries: int = 3) -> bool | None | Any:
    """Move to element with exception handling."""
    def _move():
        try:
            element = WebDriverWait(driver, timeout).until(EC.visibility_of_element_located(locator))
            actions = ActionChains(driver)
            actions.move_to_element(element).perform()
            time.sleep(0.3)
            return True
        except TimeoutException:
            logger.error(f"Element not visible for hover within {timeout} seconds: {locator}")
            return False
        except WebDriverException as e:
            logger.error(f"Action chain error: {e}")
            return False

    try:
        return safe_execute_with_retry(_move, max_retries)
    except Exception as e:
        logger.error(f"Critical error in move_to_element: {e}")
        return False


def get_element_text(driver, by_locator, timeout: int = 40, default: str = "") -> str:
    """Get element text with exception handling and default value."""
    try:
        element = WebDriverWait(driver, timeout).until(EC.visibility_of_element_located(by_locator))
        text = element.text.strip()
        return text if text else default
    except TimeoutException:
        logger.warning(f"Element not visible for text extraction within {timeout} seconds: {by_locator}")
        return default
    except (NoSuchElementException, WebDriverException) as e:
        logger.error(f"Error getting element text: {e}")
        return default
    except Exception as e:
        logger.error(f"Unexpected error in get_element_text: {e}")
        return default


def checkbox_is_checked(driver, by_locator, timeout: int = 10) -> bool:
    """Check if checkbox is checked with exception handling."""
    try:
        element = WebDriverWait(driver, timeout).until(EC.presence_of_element_located(by_locator))
        return element.is_selected()
    except TimeoutException:
        logger.warning(f"Checkbox not found within {timeout} seconds: {by_locator}")
        return False
    except (NoSuchElementException, WebDriverException) as e:
        logger.error(f"Error checking checkbox state: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in checkbox_is_checked: {e}")
        return False


def get_undetected_driver(headless: bool = False, max_retries: int = 3) -> Optional[webdriver.Chrome]:
    """Create Chrome driver with error handling (Selenium Manager resolves chromedriver)."""
    for attempt in range(max_retries):
        driver = None
        try:
            options = webdriver.ChromeOptions()
            path = os.path.join(BASE_DIR, "chrome-dir")
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create chrome directory: {e}")
                path = None

            if path:
                options.add_argument(f"--user-data-dir={path}")

            # prefs = {
            #     "download.default_directory": download_dir,
            #     "download.prompt_for_download": False,
            #     "directory_upgrade": True,
            #     "safebrowsing.enabled": True,
            # }
            # options.add_experimental_option("prefs", prefs)

            options.add_argument("--log-level=3")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-background-timer-throttling")
            options.add_argument("--disable-backgrounding-occluded-windows")
            options.add_argument("--disable-renderer-backgrounding")
            options.add_argument("--disable-features=TranslateUI")
            options.add_argument("--disable-ipc-flooding-protection")

            if headless:
                options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")
            else:
                options.add_argument("--start-maximized")

            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            # An unexpected JS alert/confirm (e.g. "Are you sure?") would otherwise make
            # every later Selenium call raise UnexpectedAlertPresentException.
            options.set_capability("unhandledPromptBehavior", "accept")

            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(90)
            time.sleep(2)

            # Apply stealth tweaks to every page that loads (not just the blank start page)
            try:
                driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                """})
            except Exception:
                pass

            driver.get("data:,")
            logger.info(f"Chrome driver initialized successfully (attempt {attempt + 1})")
            return driver

        except Exception as e:
            logger.error(f"Driver creation attempt {attempt + 1} failed: {e}")
            if "user data directory is already in use" in str(e).lower():
                logger.error("Another Chrome window is using the 'chrome-dir' profile. Close it (or kill leftover chrome.exe) and rerun.")
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            if attempt < max_retries - 1:
                time.sleep(3)

    logger.error("Max retries exceeded. Could not create the driver.")
    return None


def check_element_exists(driver, by_locator, timeout: int = 3) -> bool:
    """Check if element exists with proper exception handling."""
    try:
        WebDriverWait(driver, timeout).until(EC.visibility_of_element_located(by_locator))
        return True
    except TimeoutException:
        return False
    except (NoSuchElementException, WebDriverException):
        return False
    except Exception as e:
        logger.error(f"Unexpected error in check_element_exists: {e}")
        return False


def select_by_text(driver, by_locator, text: str, timeout: int = 10) -> bool:
    """Select dropdown option by text with exception handling."""
    try:
        select_element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(by_locator))
        select = Select(select_element)

        # Check if option exists
        options = [option.text.strip() for option in select.options]
        if text not in options:
            logger.error(f"Option '{text}' not found. Available options: {options}")
            return False

        select.select_by_visible_text(text)
        time.sleep(0.5)

        # Verify selection
        selected_option = select.first_selected_option.text.strip()
        if selected_option != text:
            logger.warning(f"Selection verification failed. Expected: '{text}', Selected: '{selected_option}'")
            return False

        return True
    except TimeoutException:
        logger.error(f"Select element not found within {timeout} seconds: {by_locator}")
        return False
    except (NoSuchElementException, ElementNotInteractableException) as e:
        logger.error(f"Select operation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in select operation: {e}")
        return False


def wait_for_page_load(driver, timeout: int = 30) -> bool:
    """Wait for page to fully load with exception handling."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(1)  # Additional buffer
        return True
    except TimeoutException:
        logger.warning(f"Page load timeout after {timeout} seconds")
        return False
    except WebDriverException as e:
        logger.error(f"Error waiting for page load: {e}")
        return False


def safe_navigate_to_url(driver, url: str, max_retries: int = 3) -> bool:
    """Navigate to URL with retry logic and exception handling."""
    for attempt in range(max_retries):
        try:
            driver.get(url)
            if wait_for_page_load(driver):
                logger.info(f"Successfully navigated to: {url}")
                return True
            else:
                logger.warning(f"Page load incomplete for: {url}")
        except WebDriverException as e:
            logger.error(f"Navigation attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue

    logger.error(f"Failed to navigate to {url} after {max_retries} attempts")
    return False


def get_element_attribute(driver, by_locator, attribute: str, timeout: int = 10, default: str = "") -> str:
    """Get element attribute with exception handling."""
    try:
        element = WebDriverWait(driver, timeout).until(EC.presence_of_element_located(by_locator))
        attr_value = element.get_attribute(attribute)
        return attr_value if attr_value is not None else default
    except TimeoutException:
        logger.warning(f"Element not found for attribute '{attribute}' within {timeout} seconds: {by_locator}")
        return default
    except Exception as e:
        logger.error(f"Error getting element attribute '{attribute}': {e}")
        return default


def wait_while_element_is_displaying(driver, by, identifier, timeout=10):
    """Waits while the specified element is displayed."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            element = driver.find_element(by, identifier)
            if not element.is_displayed():
                return
        except Exception:
            return
        time.sleep(0.5)
    logger.warning(f"Timeout waiting for element {identifier} to stop displaying.")
