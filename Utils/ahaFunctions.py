import os
import re
import time
from dotenv import load_dotenv
from typing import Optional
from Utils.pageSelectors import QuickLinks, AHALoginPage, AHAInventoryPage, AssignToInstructorPage, AssignToTrainingCenterPage
from selenium.webdriver.common.by import By
from Utils.functions import validate_environment_variables, logger, get_available_courses
from Utils.utils import (
    input_element, select_by_text, move_to_element,
    get_element_text, check_element_exists,
    click_element_by_js, safe_navigate_to_url
)

load_dotenv()
available_courses = get_available_courses()


def is_ecards_under_maintenance(driver) -> bool:
    return check_element_exists(driver, AHAInventoryPage.maintenance_message, timeout=2)


def get_ecards_error(driver) -> Optional[str]:
    """Return the text of a visible eCards error message, if any."""
    try:
        for element in driver.find_elements(*AHAInventoryPage.error_messages):
            text = element.text.strip()
            if element.is_displayed() and len(text) > 3 and set(text) != {"*"}:
                return text[:300]
    except Exception:
        pass
    return None


def finish_assignment(driver) -> bool:
    """
    Click Complete and make sure eCards accepted the assignment:
    no error after Confirm/Validate or after Complete, and the
    confirmation page ('Go To Inventory') is shown.
    """
    time.sleep(1)
    error = get_ecards_error(driver)
    if error:
        logger.error(f"eCards error before Complete: {error}")
        return False

    if not click_element_by_js(driver, AHAInventoryPage.finish_button):
        logger.error("Failed to click Complete")
        return False
    time.sleep(2)

    error = get_ecards_error(driver)
    if error:
        logger.error(f"eCards error after Complete: {error}")
        return False

    if not check_element_exists(driver, AHAInventoryPage.go_to_inventory_button, timeout=15):
        logger.error("eCards did not show the confirmation page after Complete")
        return False

    if not click_element_by_js(driver, AHAInventoryPage.go_to_inventory_button):
        safe_navigate_to_url(driver, QuickLinks.ecards_inventory)
    time.sleep(2)
    return True


def get_inventory_quantity(driver, product_code: str) -> Optional[int]:
    """
    Live quantity of one product on the eCards inventory page.
    0 if the product isn't listed (rows disappear at 0), None if the page didn't load.
    """
    try:
        if not safe_navigate_to_url(driver, QuickLinks.ecards_inventory):
            return None
        if not check_element_exists(driver, AHAInventoryPage.stock_id(4), timeout=20):
            return None
        codes = driver.find_elements(*AHAInventoryPage.stock_id(4))
        quantities = driver.find_elements(*AHAInventoryPage.stock_id(3))
        for code_element, quantity_element in zip(codes, quantities):
            if code_element.text.strip() == product_code:
                quantity = quantity_element.text.strip().replace(",", "")
                return int(quantity) if quantity.isdigit() else 0
        return 0
    except Exception as e:
        logger.error(f"Could not read inventory for {product_code}: {e}")
        return None


def login_to_ecards(driver, username=os.getenv("ATLAS_USERNAME"), password=os.getenv("ATLAS_PASSWORD")) -> bool:
    """Login to eCards with comprehensive error handling and retry logic."""
    other_account = check_element_exists(driver, (By.XPATH, "//label[text()= 'Training Site']"), timeout=3)
    if other_account:
        logout_from_aha(driver)
    if not validate_environment_variables():
        return False
    try:
        # Check if already logged in
        if "https://ecards.heart.org/inventory" == driver.current_url:
            return True

        # Check for sign-in button
        sign_in_button = check_element_exists(driver, AHALoginPage.sign_in_link, timeout=3)


        if sign_in_button:
            if not click_element_by_js(driver, AHALoginPage.sign_in_link):
                return False

            time.sleep(3)

            # Check if redirected to inventory
            if "inventory" in driver.current_url:
                return True

        # Proceed with login if email field exists
        if check_element_exists(driver, AHALoginPage.username_input, timeout=5):
            if not input_element(driver, AHALoginPage.username_input, username):
                return False

            time.sleep(1)

            if not input_element(driver, AHALoginPage.password_input, password):
                return False

            time.sleep(1)

            # Try to click remember me checkbox (optional)
            # remember_me_xpath = "//input[@id= 'RememberMe']/following-sibling::label"
            # if check_element_exists(driver, (By.XPATH, remember_me_xpath), timeout=3):
            #     click_element_by_js(driver, (By.XPATH, remember_me_xpath))
            #
            # time.sleep(1)

            # Click sign-in button
            if not click_element_by_js(driver, AHALoginPage.sign_in_button):
                return False

            time.sleep(5)

            # Verify login success
            if "https://ecards.heart.org/inventory" == driver.current_url:
                return True
            else:
                return False
        else:
            return True

    except:
        logger.error("Failed to login to Atlas")
        return False


def assign_to_instructor(driver, name: str, quantity: str, product_code: str) -> bool:
    """Assign to instructor with comprehensive error handling."""
    if not available_courses:
        logger.error("Available courses not initialized")
        return False

    try:
        # Click on the course
        if not click_element_by_js(driver, (By.XPATH, f"{AHAInventoryPage.available_course_selector(product_code)}[@role='button']")):
            return False

        time.sleep(1)

        # Click 'Assign to Instructor'
        if not click_element_by_js(driver, AHAInventoryPage.assign_to('Instructor')):
            return False

        # Select TC Admin role
        if not select_by_text(driver, AssignToInstructorPage.role_select, 'TC Admin'):
            return False

        # Select course
        course_name_on_ecard = available_courses.course_name_on_eCard(product_code)
        if not course_name_on_ecard:
            logger.error(f"Course name not found for product code: {product_code}")
            return False

        if not select_by_text(driver, AssignToInstructorPage.course_select, course_name_on_ecard):
            return False

        # Select training center
        if not select_by_text(driver, AssignToInstructorPage.training_center_select, 'Shell CPR, LLC.'):
            return False

        # Click assign to dropdown
        if not click_element_by_js(driver, AssignToInstructorPage.instructor_select):
            return False

        # Select instructor by name
        instructor_name = format_name(name)
        if not click_element_by_js(driver, AssignToInstructorPage.instructor_name_selector(instructor_name)):
            return False

        # Click move next
        if not click_element_by_js(driver, AssignToInstructorPage.submit_button):
            return False

        # Input quantity
        if not input_element(driver, AssignToInstructorPage.quantity_input, str(quantity)):
            return False

        # Click confirm
        if not click_element_by_js(driver, AssignToInstructorPage.continue_button):
            return False

        # Click complete and confirm eCards accepted it
        if not finish_assignment(driver):
            return False

        logger.info(f"Successfully assigned {quantity} of {product_code} ({'Individual' if available_courses.is_individual_course(product_code) else 'Bundle'}) to instructor {name}")
        time.sleep(2)
        return True

    except Exception as e:
        time.sleep(3)
        logger.error(f"Error occurred while assigning to instructor: {e}")
        return False

    logger.error("Failed to assign to instructor")
    return False


def assign_to_training_center(driver, name: str, quantity: str, product_code: str, training_site: str,
                              result: Optional[dict] = None) -> bool:
    """Assign to training center with comprehensive error handling.

    For 'Code Blue CPR Services, LLC' (TS68082) this is the full Code Blue flow:
      1. assign from the main account to the Code Blue training site
      2-3. log out, log into the Code Blue account (AHA_NEW_USERNAME / AHA_NEW_PASSWORD)
      4. assign the eCards from the Code Blue account to the instructor
      5-6. log out and log back into the main account
    If a `result` dict is passed, 'site_assigned' is set after step 1 and the Code Blue
    step fills in its own keys (see assign_from_code_blue_account).
    """
    if not available_courses:
        logger.error("Available courses not initialized")
        return False

    # Check if this is appropriate for training site assignment
    if available_courses.is_individual_course(product_code):
        logger.info(f"Course {product_code} is an individual course - typically assigned to instructors, but proceeding with training site assignment as requested")

    try:
        available_course_selector = f"{AHAInventoryPage.available_course_selector(product_code)}[@role='button']"
        # Click on the course
        if not click_element_by_js(driver, (By.XPATH, available_course_selector)):
            return False

        time.sleep(1)

        # Click 'Assign to Training Site'
        if not click_element_by_js(driver, AHAInventoryPage.assign_to('Training Site')):
            return False

        # Select training center
        if not select_by_text(driver, AssignToTrainingCenterPage.training_center_select, 'Shell CPR, LLC.'):
            return False

        # Select training site
        if not select_by_text(driver, AssignToTrainingCenterPage.training_site_select, training_site):
            return False

        # Select course
        course_name_on_ecard = available_courses.course_name_on_eCard(product_code)
        if not course_name_on_ecard:
            logger.error(f"Course name not found for product code: {product_code}")
            return False

        if not select_by_text(driver, AssignToTrainingCenterPage.course_select, course_name_on_ecard):
            return False

        # Input quantity
        if not input_element(driver, AssignToTrainingCenterPage.quantity_input, str(quantity)):
            return False

        # Click validate
        if not click_element_by_js(driver, AssignToTrainingCenterPage.submit_button):
            return False

        # Click complete and confirm eCards accepted it
        if not finish_assignment(driver):
            return False

        if training_site != 'Code Blue CPR Services, LLC':
            time.sleep(2)
            return True

        if result is not None:
            result["site_assigned"] = True
        logger.info(f"Assigned {quantity} of {product_code} to training site {training_site}; continuing as the Code Blue account")
        return assign_from_code_blue_account(driver, name, quantity, product_code, training_site,
                                             available_course_selector, result=result)

    except Exception as e:
        logger.error(f"Training site assignment failed: {e}")
        time.sleep(3)
        return False


def assign_from_code_blue_account(driver, name: str, quantity: str, product_code: str, training_site: str,
                                  available_course_selector: str, result: Optional[dict] = None) -> bool:
    """Code Blue: log in as the Code Blue account and assign the cards on to the instructor.
    Always logs back into the main (Atlas) account afterwards, even if a step fails.

    If a `result` dict is passed it is filled with:
      before / after – Code Blue account stock of the product before and after the assignment
      short          – True if the Code Blue account doesn't have enough stock (nothing assigned)
      committed      – True once Confirm was clicked (cards may have been issued from here on)
    """
    try:
        logout_from_aha(driver)
        safe_navigate_to_url(driver, QuickLinks.ecards_inventory)
        if not login_to_ecards(driver, username=os.getenv("AHA_NEW_USERNAME"), password=os.getenv("AHA_NEW_PASSWORD")):
            logger.error("Could not log into the Code Blue eCards account")
            return False

        if result is not None:
            # Stock in the Code Blue account (also opens the inventory page for the next click)
            result["before"] = get_inventory_quantity(driver, product_code)
            if result["before"] is None:
                logger.error(f"Could not read Code Blue account stock for {product_code}")
                return False
            if result["before"] < int(quantity):
                logger.error(f"Code Blue account has {result['before']} of {product_code}, need {quantity}")
                result["short"] = True
                return False

        if not click_element_by_js(driver, (By.XPATH, available_course_selector)):
            return False

        # Click 'Assign to Instructor'
        if not click_element_by_js(driver, AHAInventoryPage.assign_to('Instructor')):
            return False

        if not select_by_text(driver, AssignToInstructorPage.role_select, 'TSC'):
            logger.error("Failed to select TS Admin")
            return False

        # Select course
        course_name_on_ecard = available_courses.course_name_on_eCard(product_code)
        if not course_name_on_ecard:
            logger.error(f"Course name not found for product code: {product_code}")
            return False

        if not select_by_text(driver, AssignToInstructorPage.course_select, course_name_on_ecard):
            return False

        # Select training center
        if not select_by_text(driver, AssignToInstructorPage.training_center_select, 'Shell CPR, LLC.'):
            return False

        time.sleep(1)

        # Select training site
        if not select_by_text(driver, AssignToInstructorPage.training_site_select, training_site):
            return False

        time.sleep(1)

        # Click assign to dropdown
        if not click_element_by_js(driver, AssignToInstructorPage.instructor_select):
            return False

        time.sleep(1)

        # Select instructor by name
        instructor_name = format_name(name)
        if not click_element_by_js(driver, AssignToInstructorPage.instructor_name_selector(instructor_name)):
            return False

        time.sleep(1)

        # Click move next
        if not click_element_by_js(driver, AssignToInstructorPage.submit_button):
            return False

        time.sleep(1)

        # Input quantity
        if not input_element(driver, AssignToInstructorPage.quantity_input, str(quantity)):
            return False

        time.sleep(1)

        # Click confirm
        if result is not None:
            result["committed"] = True
        if not click_element_by_js(driver, AssignToInstructorPage.continue_button):
            return False

        time.sleep(1)

        # Click complete and confirm eCards accepted it
        if not finish_assignment(driver):
            return False

        if result is not None:
            result["after"] = get_inventory_quantity(driver, product_code)

        logger.info(f"Successfully assigned {quantity} of {product_code} to instructor {name} from the Code Blue account")
        return True

    except Exception as e:
        logger.error(f"Code Blue assignment failed: {e}")
        return False
    finally:
        logout_from_aha(driver)
        safe_navigate_to_url(driver, QuickLinks.ecards_inventory)
        login_to_ecards(driver, username=os.getenv("ATLAS_USERNAME"), password=os.getenv("ATLAS_PASSWORD"))


def logout_from_aha(driver):
    try:
        click_element_by_js(driver, (By.XPATH, "//img[@id= 'profileImg']/parent::button"))
        click_element_by_js(driver, (By.ID, "logoutId"))
        time.sleep(1)
        header_username = (By.XPATH, "//span[contains(@class, 'Header_userName')]/ancestor::button")
        ele = check_element_exists(driver, header_username)
        if not ele:
            return
        move_to_element(driver, header_username)
        click_element_by_js(driver, (By.XPATH, "//a[text()= 'Logout']"))
    except Exception as e:
        logger.error(f"Error during logout from AHA: {e}")


def assign_to_admin_instructor(driver, name: str, quantity: str, product_code: str) -> bool:
    """Assign to Admin Instructor - For ACLS/PALS courses."""
    if not available_courses:
        logger.error("Available courses not initialized")
        return False

    logger.info(f"Assigning {quantity} of {product_code} to Admin Instructor for {name}")
    try:
        safe_navigate_to_url(driver, QuickLinks.ecards_instructor_assignment)

        time.sleep(2)

        # Step 3: Select TS Admin role
        if not select_by_text(driver, AssignToInstructorPage.role_select, 'TS Admin'):
            logger.error("Failed to select TS Admin")
            return False

        # Step 4: Select course
        course_name_on_ecard = available_courses.course_name_on_eCard(product_code)
        if not course_name_on_ecard:
            logger.error(f"Course name not found for product code: {product_code}")
            return False

        if not select_by_text(driver, AssignToInstructorPage.course_select, course_name_on_ecard):
            logger.error("Failed to select course for Admin Instructor")
            return False

        # Step 5: Select Training Center
        if not select_by_text(driver, AssignToInstructorPage.training_center_select, 'CPR Suppliers, LLC'):
            logger.error("Failed to select Training Center")
            return False

        # Step 6: Select Training Site
        if not select_by_text(driver, AssignToInstructorPage.training_site_select, 'Shell CPR'):
            logger.error("Failed to select Training Site")
            return False

        # Step 7: Select Instructor
        if not click_element_by_js(driver, AssignToInstructorPage.instructor_select):
            logger.error("Failed to open instructor dropdown")
            return False

        time.sleep(1)

        instructor_name = format_name(name)
        if not click_element_by_js(driver, AssignToInstructorPage.instructor_name_selector(instructor_name)):
            logger.error(f"Failed to select instructor: {name}")
            return False

        # Step 8: Click Submit button
        if not click_element_by_js(driver, AssignToInstructorPage.submit_button):
            logger.error("Failed to click Submit button")
            return False

        time.sleep(1)

        # Check available quantity
        available_qyt_element = get_element_text(driver, AssignToInstructorPage.available_quantity, default="0")
        available_qyt = int(available_qyt_element) if available_qyt_element.isdigit() else 0

        if available_qyt < int(quantity):
            logger.warning(f"Insufficient quantity for {product_code}. Available: {available_qyt}, Required: {quantity}")

            # Navigate back to inventory without retrying
            try:
                # Try to go back to inventory directly
                if click_element_by_js(driver, (By.XPATH, "//a[text()= 'Go To Inventory']")):
                    logger.info("Successfully returned to inventory due to insufficient quantity")
                else:
                    # Alternative method: try to navigate back via browser back
                    driver.get("https://ecards.heart.org/Inventory")
                    time.sleep(2)
                    logger.info("back to inventory via URL navigation")
            except Exception as nav_error:
                logger.error(f"Error navigating back to inventory: {nav_error}")

            return False  # Return False but don't retry

        # Input quantity
        if not input_element(driver, AssignToInstructorPage.quantity_input, str(quantity)):
            logger.error("Failed to input quantity")
            return False

        # Click confirm
        if not click_element_by_js(driver, AssignToInstructorPage.continue_button):
            logger.error("Failed to confirm assignment")
            return False

        time.sleep(1)

        # Click complete and confirm eCards accepted it
        if not finish_assignment(driver):
            return False

        logger.info(f"Successfully assigned {quantity} of {product_code} (ACLS/PALS) to Admin Instructor for {name}")
        time.sleep(2)
        return True

    except Exception as e:
        logger.error(f"Admin Instructor assignment failed: {e}")
        return False


def format_name(name: str) -> str:
    """Format a full name with smart title casing (handles Mc, Mac, O', and hyphens)."""

    def smart_cap(word: str) -> str:
        # Handle hyphenated names (e.g., Abdul-Majied, Anne-Marie)
        if "-" in word:
            return "-".join(smart_cap(part) for part in word.split("-"))

        # Base capitalization (e.g., "donna" -> "Donna")
        w = word.capitalize()

        # Handle O' prefix (e.g., O'Neil, O'Connor)
        if re.match(r"^o'[a-z]", word.lower()):
            return "O'" + word[2:].capitalize()

        # Handle Mc prefix (e.g., McKinney, McDonald, McCarty)
        if word.lower().startswith("mc") and len(word) > 2:
            return "Mc" + word[2].upper() + word[3:].lower()

        # Handle Mac prefix (e.g., MacArthur, MacGregor)
        if word.lower().startswith("mac") and len(word) > 3:
            return "Mac" + word[3].upper() + word[4:].lower()

        return w

    return " ".join(smart_cap(word) for word in name.split())


def get_stock_info(driver) -> dict[str, int]:
    """Get stock information from the inventory page, keyed by product code."""
    stock_info = {}
    try:
        product_codes = driver.find_elements(*AHAInventoryPage.stock_id(4))
        product_quantities = driver.find_elements(*AHAInventoryPage.stock_id(3))

        # Get stock information for non-ACLS/PALS courses only
        for code_element, quantity_element in zip(product_codes, product_quantities):
            code = code_element.text.strip()
            quantity = quantity_element.text.strip()
            quantity_int = int(quantity) if quantity.isdigit() else 0
            if code and quantity_int > 0:
                stock_info[code] = quantity_int

        # Get stock information for ACLS/PALS courses
        courses_to_check = [
            {"product_code": "25-3000", "name": "ACLS Provider Course"},
            {"product_code": "25-3006", "name": "PALS Provider Course"}
        ]

        safe_navigate_to_url(driver, QuickLinks.ecards_instructor_assignment)

        for i, course in enumerate(courses_to_check):
            if i == 0:
                select_by_text(driver, AssignToInstructorPage.role_select, 'TS Admin')
            select_by_text(driver, AssignToInstructorPage.course_select, course.get("name", ""))
            select_by_text(driver, AssignToInstructorPage.training_center_select, 'CPR Suppliers, LLC')
            select_by_text(driver, AssignToInstructorPage.training_site_select, 'Shell CPR')

            time.sleep(1)

            available_qyt_element = get_element_text(driver, (By.ID, "availQty"), default="0")
            available_qyt = int(available_qyt_element) if available_qyt_element.isdigit() else 0
            product_code = course.get("product_code", "")
            if product_code and available_qyt > 0:
                stock_info[product_code] = available_qyt

    except Exception as e:
        logger.error(f"Error retrieving stock information: {e}")
    return stock_info
