import os
import re
import time
from selenium.webdriver.common.by import By
from typing import Tuple, List, Dict, Any, Optional
from Utils.pageSelectors import (
    QuickLinks,
    EnrollNationwideLoginPage,
    EnrollNationwideOrdersList,
    EnrollNationwideOrderPage
)
from Utils.utils import (
    logger,
    input_element,
    check_element_exists,
    click_element_by_js,
    safe_navigate_to_url,
    wait_for_page_load
)

# Orders in these statuses still need eCards. Everything except "completed".
STATUSES_TO_PROCESS = ["new", "viewed", "pending"]
MAX_LIST_PAGES = 25
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def login_to_enrollNationwide(driver, username, password) -> bool:
    """Log in to Enroll Nationwide (no-op if the session is still valid). Returns True on success."""
    try:
        if not safe_navigate_to_url(driver, QuickLinks.dashboard):
            logger.error("Failed to navigate to EnrollNationwide dashboard/login page")
            return False

        # Login form visible -> not logged in (session expired or first run)
        if check_element_exists(driver, EnrollNationwideLoginPage.username_input, timeout=5):
            if not input_element(driver, EnrollNationwideLoginPage.username_input, username):
                logger.error("Failed to input username")
                return False
            if not input_element(driver, EnrollNationwideLoginPage.password_input, password):
                logger.error("Failed to input password")
                return False

            # Optional - don't spend 30s retrying if it's not there
            click_element_by_js(driver, EnrollNationwideLoginPage.remember_me_checkbox, timeout=3, max_retries=1)
            time.sleep(1)

            if not click_element_by_js(driver, EnrollNationwideLoginPage.login_button):
                logger.error("Failed to click login button")
                return False
            wait_for_page_load(driver)

        if check_element_exists(driver, EnrollNationwideLoginPage.info_needed_popup, timeout=3):
            click_element_by_js(driver, EnrollNationwideLoginPage.info_needed_popup, timeout=3, max_retries=1)
            logger.info("Clicked on 'Info Needed' popup")
            wait_for_page_load(driver)

        # Verify: the login form must be gone
        if check_element_exists(driver, EnrollNationwideLoginPage.username_input, timeout=3):
            logger.error("Login to EnrollNationwide failed - still on the login page (check ENW_USERNAME/ENW_PASSWORD)")
            return False

        if 'account' not in driver.current_url.lower():
            logger.warning(f"Logged in, but unexpected URL: {driver.current_url}")
        logger.info("Logged into EnrollNationwide")
        return True

    except Exception as e:
        logger.error(f"An error occurred during login to EnrollNationwide: {e}")
        return False


def get_order_id(order_link: str) -> str:
    match = re.search(r"[?&]order=(\d+)", order_link or "")
    return match.group(1) if match else ""


def get_orders_to_process(driver) -> List[str]:
    """
    Collect links of AHA orders that are paid and not completed yet.
    Each status is opened as its own filtered list (os=new / viewed / pending) and every
    page is followed, so older open orders on page 2+ are not missed.
    """
    order_links: List[str] = []

    for status in STATUSES_TO_PROCESS:
        url = QuickLinks.aha_orders_by_status(status)
        for _ in range(MAX_LIST_PAGES):
            if not safe_navigate_to_url(driver, url):
                logger.error(f"Failed to open the '{status}' orders list")
                break

            if check_element_exists(driver, EnrollNationwideOrdersList.order_rows, timeout=5):
                for row in driver.find_elements(*EnrollNationwideOrdersList.order_rows):
                    try:
                        row_status = row.find_element(*EnrollNationwideOrdersList.row_status).text.strip().lower()
                        payment = row.find_element(*EnrollNationwideOrdersList.row_payment).text.strip().lower()
                        link = row.get_attribute("href")
                        if row_status == "completed" or not link:
                            continue
                        if payment != "paid":
                            number = row.find_element(*EnrollNationwideOrdersList.row_order_number).text.strip()
                            logger.info(f"Skipping {number}: payment status is '{payment}'")
                            continue
                        if link not in order_links:
                            order_links.append(link)
                    except Exception:
                        continue

            next_links = driver.find_elements(*EnrollNationwideOrdersList.next_page_link)
            if not next_links:
                break
            url = next_links[0].get_attribute("href")

    # oldest orders first
    order_links.sort(key=lambda link: int(get_order_id(link) or 0))
    logger.info(f"Found {len(order_links)} order(s) to process: {[get_order_id(l) for l in order_links]}")
    return order_links


def get_order_data(driver) -> Tuple[List[Dict[str, Any]], int]:
    """Read instructor, training site and ordered items from the open order page."""
    try:
        if not check_element_exists(driver, EnrollNationwideOrderPage.order_details, timeout=15):
            logger.error("Order details not found on the page")
            return [], 0

        order_data = []
        ordered_by = driver.find_element(*EnrollNationwideOrderPage.ordered_by_box)

        # "Ordered by" lists the training site first, then the instructor.
        # Training-site sales only show the instructor, so don't rely on fixed positions.
        names = [el.text.strip() for el in ordered_by.find_elements(*EnrollNationwideOrderPage.ordered_by_names) if el.text.strip()]
        if len(names) >= 2:
            training_site, name = names[0], names[1]
        elif len(names) == 1:
            training_site, name = "", names[0]
        else:
            logger.error("Instructor name not found on the order")
            return [], 0

        # The page turns the email into a Gmail link, so read it from the text
        email_match = EMAIL_PATTERN.search(ordered_by.text)
        email = email_match.group(0) if email_match else ""

        # The header and total rows have extra classes, so these are only the item rows
        for product in driver.find_elements(*EnrollNationwideOrderPage.ordered_products):
            try:
                course_name = product.find_element(By.XPATH, "./span[1]/strong").text.strip()
                sku = product.find_element(By.XPATH, "./span[2]").text.strip()
                quantity = re.sub(r"[^\d]", "", product.find_element(By.XPATH, "./span[3]").text)

                if sku in ("—", "–", "-"):
                    sku = ""  # product no longer listed; main.py skips these orders

                order_data.append({
                    "training_site": training_site,
                    "name": name,
                    "quantity": quantity or "0",
                    "product_code": sku,
                    "course_name": course_name,
                    "email": email
                })
            except Exception as e:
                logger.warning(f"Could not read an order line: {e}")
                continue

        return order_data, len(order_data)

    except Exception as e:
        logger.error(f"Critical error in get_order_data: {e}")
        return [], 0


def get_order_status(driver) -> Tuple[str, str]:
    """Return (order status, payment status) from the open order page, e.g. ('viewed', 'paid')."""
    status, payment = "", ""
    try:
        checked = driver.find_elements(*EnrollNationwideOrderPage.checked_status)
        status = checked[0].get_attribute("value").strip().lower() if checked else ""
        pay_select = driver.find_elements(*EnrollNationwideOrderPage.payment_status_select)
        payment = pay_select[0].get_attribute("value").strip().lower() if pay_select else ""
    except Exception as e:
        logger.error(f"Could not read order status: {e}")
    return status, payment


def mark_order_as_complete(driver, order_link: str) -> bool:
    """
    Select 'Completed', press 'Update & send email', then reload the order and
    confirm the status really is Completed.
    """
    try:
        if not click_element_by_js(driver, EnrollNationwideOrderPage.complete_order_button):
            logger.error("Failed to select 'Completed' status")
            return False

        if not click_element_by_js(driver, EnrollNationwideOrderPage.status_update_button):
            logger.error("Failed to click 'Update & send email'")
            return False

        time.sleep(3)
        wait_for_page_load(driver)

        # Verify on a fresh load of the order
        if not safe_navigate_to_url(driver, order_link):
            logger.error("Could not reload the order to verify its status")
            return False
        status, _ = get_order_status(driver)
        if status != "completed":
            logger.error(f"Order status is '{status}' after update, expected 'completed'")
            return False

        logger.info("Successfully marked order as complete")
        return True

    except Exception as e:
        logger.error(f"Mark complete attempt failed: {e}")
        return False
