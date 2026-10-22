import os
import time
import logging

from datetime import datetime
from typing import List, Dict, Any, Optional
from courses import AvailableCourses
from discord_notification import DiscordNotifier, generate_stock_message
from Utils.functions import get_training_site_name, validate_environment_variables
from Utils.orderLedger import OrderLedger, ProcessedOrders
from Utils.pageSelectors import QuickLinks, EnrollNationwideOrderPage, AHAInventoryPage
from Utils.utils import get_undetected_driver, safe_navigate_to_url

from Utils.codeBlueFunctions import (
    login_to_enrollNationwide, get_orders_to_process,
    get_order_data, get_order_status, get_order_id,
    mark_order_as_complete, STATUSES_TO_PROCESS
)

from Utils.ahaFunctions import (
    login_to_ecards, assign_to_instructor,
    assign_to_training_center, assign_to_admin_instructor,
    get_stock_info, get_inventory_quantity, is_ecards_under_maintenance,
    assign_from_code_blue_account
)

# Code Blue CPR Services orders (training site TS68082 in data/training_sites.csv):
# assign from the main account to the Code Blue site, then from the Code Blue account
# to the instructor (see assign_to_training_center in ahaFunctions.py).
CODE_BLUE_SITE_CODE = "TS68082"
CODE_BLUE_SITE_TEXT = "code blue cpr services"
CODE_BLUE_ECARDS_SITE = get_training_site_name(CODE_BLUE_SITE_CODE) or "Code Blue CPR Services, LLC"


last_message = ""
quantity_required = []   # stock shortages found during the current run
needs_review = []        # orders that need a person to check eCards

# DRY_RUN=true in .env: read stock and orders and log what would happen, without
# assigning any eCards or changing any order.
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")


# Setup logging
logger = logging.getLogger(__name__)

# Log startup information
print("=" * 50)
print("ENROLLNATIONWIDE AUTOMATION STARTING" + (" (DRY RUN)" if DRY_RUN else ""))
print("=" * 50)


def is_acls_pals_course(course_name: str) -> bool:
    """Check if course is ACLS or PALS based on course name."""
    if not course_name:
        return False

    course_upper = course_name.upper()
    return 'ACLS' in course_upper or 'PALS' in course_upper


def get_training_site_name_for_order(training_site: str) -> str:
    """
    Get the eCards training site name for an Enroll Nationwide site label,
    e.g. 'TS26570 Concierge Healthcare Training Services'.
    data/training_sites.csv wins; otherwise the text after the TS code is used.
    """
    training_site = (training_site or "").strip()
    code = training_site.split(' ')[0].strip() if ' ' in training_site else training_site
    training_site_name = get_training_site_name(code)
    if training_site_name:
        return training_site_name
    if code.upper().startswith("TS") and training_site[len(code):].strip():
        return training_site[len(code):].strip(" -–,")
    return training_site or "Unknown Training Site"


class OrderProcessor:
    def __init__(self):
        self.available_courses = None
        self.driver = None
        self.stock_info = {}
        self.ledger = OrderLedger()
        self.processed_orders = ProcessedOrders()
        self.skip_reason = ""   # why the last order was skipped (saved in processed_orders.json)
        self.current_order_name = ""
        self.current_order_site = ""        # training site / instructor of the order being processed,
        self.current_order_instructor = ""  # shown in the Discord stock message
        self.ecards_tab = None
        self.enw_tab = None
        self.results = {"completed": [], "skipped": [], "failed": [], "short": [], "review": [], "dry-run": [], "waiting": []}

    def initialize(self) -> bool:
        """Initialize the order processor with safe exception handling."""
        try:
            logger.info("Initializing automation components...")
            self.available_courses = AvailableCourses()

            self.driver = get_undetected_driver()
            if self.driver:
                self.ecards_tab = self.driver.current_window_handle
                logger.info("Chrome driver initialized successfully")
                return True
            else:
                logger.error("Failed to initialize Chrome driver")
                return False
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    def cleanup(self):
        """Phase 4: close the driver."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Resources cleaned up successfully")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")

    def switch_to(self, handle):
        if handle and self.driver.current_window_handle != handle:
            self.driver.switch_to.window(handle)

    # ------------------------------------------------------------------ #
    # eCards session (stays open in its own tab for the whole run)
    # ------------------------------------------------------------------ #
    def setup_eCards_session(self) -> bool:
        """Open the eCards inventory in the eCards tab and make sure we are logged in."""
        self.switch_to(self.ecards_tab)
        for attempt in range(3):
            try:
                safe_navigate_to_url(self.driver, QuickLinks.ecards_inventory)
                time.sleep(3)

                if is_ecards_under_maintenance(self.driver):
                    logger.error("eCards site is under maintenance")
                    return False

                if not login_to_ecards(self.driver):
                    continue

                # If redirected to log in after click, try once more
                if "login" in self.driver.current_url.lower():
                    if not login_to_ecards(self.driver):
                        continue

                return True

            except Exception as e:
                logger.error(f"eCards session setup attempt {attempt + 1} failed: {e}")
                time.sleep(2)

        logger.error("Failed to setup eCards session")
        return False

    # ------------------------------------------------------------------ #
    # Phase 1
    # ------------------------------------------------------------------ #
    def refresh_stock_snapshot(self) -> bool:
        """Phase 1: log into eCards and capture the stock of every product."""
        if not self.setup_eCards_session():
            return False

        try:
            self.stock_info = get_stock_info(self.driver)
            logger.info("Captured stock snapshot for %d product codes", len(self.stock_info))
            for sku in sorted(self.stock_info):
                logger.info(f"    {sku:<10} {self.stock_info[sku]:>5}")
            return True
        except Exception as e:
            logger.error(f"Failed to capture eCards stock snapshot: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Phase 2
    # ------------------------------------------------------------------ #
    def get_orders(self) -> Optional[List[str]]:
        """Phase 2: open Enroll Nationwide in a second tab, filter orders, return their links."""
        self.driver.switch_to.new_window("tab")
        self.enw_tab = self.driver.current_window_handle

        if not login_to_enrollNationwide(self.driver, os.getenv("ENW_USERNAME"), os.getenv("ENW_PASSWORD")):
            return None
        return get_orders_to_process(self.driver)

    # ------------------------------------------------------------------ #
    # Phase 3
    # ------------------------------------------------------------------ #
    def should_skip_course(self, course_name: str, product_code: str) -> tuple[bool, str]:
        """Check if course should be skipped and return reason."""
        try:
            if 'red cross' in course_name.lower() or 'redcross' in course_name.lower():
                return True, f"Red Cross course: {course_name}"

            if not product_code:
                return True, f"'{course_name}' has no SKU on the order"

            if not self.available_courses.is_course_available(product_code):
                return True, f"Course {product_code} is not available for eCard generation"

            return False, ""
        except Exception as e:
            logger.error(f"Error checking course availability: {e}")
            return True, f"Error checking course: {e}"

    def reserve_order_stock(self, order_data: List[Dict[str, Any]], order_name: str) -> bool:
        """Check every line of the order against the run-level stock snapshot."""
        global quantity_required
        shortages = []
        for order in order_data:
            product_code = order.get('product_code', '')
            quantity_needed = int(order.get('quantity', 0))
            available_quantity = self.stock_info.get(product_code, 0)
            if available_quantity < quantity_needed:
                shortages.append({
                    "sku": product_code,
                    "qty": quantity_needed - available_quantity,
                    "required_qty": quantity_needed,
                    "available_qty": available_quantity,
                    "order_name": order_name,
                    "training_site": self.current_order_site,
                    "instructor": self.current_order_instructor,
                })

        if shortages:
            quantity_required.extend(shortages)
            logger.warning(
                "Skipping entire order because the stock snapshot is insufficient: %s",
                shortages
            )
            return False

        return True

    def assign_line_code_blue(self, order: Dict[str, Any]) -> str:
        """
        Full Code Blue flow for one line:
        main account -> Code Blue CPR Services site, then Code Blue account -> instructor,
        then back to the main account. Both halves are validated by stock.
        Returns done / failed / unverified, or 'transferred' when the cards reached the
        Code Blue account but the instructor step didn't happen (next run only redoes that step).
        """
        product_code = order.get('product_code', '')
        name = order.get('name', '')
        quantity = int(order.get('quantity', 0))

        # Main account stock before step 1
        before_main = get_inventory_quantity(self.driver, product_code)
        if before_main is None:
            logger.error(f"Could not read eCards stock for {product_code}")
            return "failed"
        if before_main < quantity:
            logger.error(f"Live stock for {product_code} is {before_main}, need {quantity}")
            quantity_required.append({"sku": product_code, "qty": quantity - before_main, "required_qty": quantity,
                                      "available_qty": before_main, "order_name": self.current_order_name,
                                      "training_site": self.current_order_site,
                                      "instructor": self.current_order_instructor})
            return "failed"

        logger.info(f"Code Blue order: assigning {quantity} x {product_code} to {CODE_BLUE_ECARDS_SITE}, "
                    f"then from the Code Blue account to {name}")
        result = {}
        ok = assign_to_training_center(self.driver, name, str(quantity), product_code,
                                       CODE_BLUE_ECARDS_SITE, result=result)

        # Step 1 check: main account stock must have dropped by the quantity
        # (assign_to_training_center always logs back into the main account at the end)
        if not self.setup_eCards_session():
            logger.error("Could not get back into the main eCards account to validate")
            return "unverified"
        after_main = get_inventory_quantity(self.driver, product_code)
        if after_main is not None:
            self.stock_info[product_code] = after_main
        transferred = after_main is not None and before_main - after_main == quantity

        if not transferred:
            if not ok and after_main == before_main and not result.get("site_assigned"):
                logger.error(f"✗ {product_code} was not assigned to {CODE_BLUE_ECARDS_SITE} (stock unchanged at {before_main})")
                return "failed"
            logger.error(f"? {product_code}: could not confirm the transfer to {CODE_BLUE_ECARDS_SITE} "
                         f"(main stock {before_main} -> {after_main})")
            return "unverified"

        logger.info(f"✓ Step 1 validated: main stock {before_main} -> {after_main}")

        # Step 4 check: Code Blue account stock must have dropped by the quantity
        cb_before, cb_after = result.get("before"), result.get("after")
        if ok and cb_before is not None and cb_after is not None and cb_before - cb_after == quantity:
            logger.info(f"✓ Step 4 validated: Code Blue account stock {cb_before} -> {cb_after}")
            return "done"
        if not result.get("committed"):
            logger.error(f"{product_code}: cards are in the Code Blue account but were not assigned to {name}; "
                         f"next run will only do the Code Blue step")
            return "transferred"
        logger.error(f"? {product_code}: could not confirm the Code Blue assignment "
                     f"(success={ok}, Code Blue stock {cb_before} -> {cb_after})")
        return "unverified"

    def assign_line_from_code_blue(self, order: Dict[str, Any]) -> str:
        """Only the Code Blue part (steps 2-6) for a line whose cards were already moved to the
        Code Blue site in an earlier run. Validated against the Code Blue account's stock."""
        product_code = order.get('product_code', '')
        name = order.get('name', '')
        quantity = int(order.get('quantity', 0))
        course_selector = f"{AHAInventoryPage.available_course_selector(product_code)}[@role='button']"

        logger.info(f"Resuming Code Blue order: assigning {quantity} x {product_code} "
                    f"to {name} from the Code Blue account")
        result = {}
        ok = assign_from_code_blue_account(self.driver, name, str(quantity), product_code,
                                           CODE_BLUE_ECARDS_SITE, course_selector, result=result)
        before, after = result.get("before"), result.get("after")

        if ok and before is not None and after is not None and before - after == quantity:
            logger.info(f"✓ Validated {product_code} (Code Blue account): stock {before} -> {after}")
            return "done"
        if not ok and result.get("short"):
            quantity_required.append({"sku": f"{product_code} (Code Blue account)", "qty": quantity - before,
                                      "required_qty": quantity, "available_qty": before,
                                      "order_name": self.current_order_name,
                                      "training_site": self.current_order_site,
                                      "instructor": self.current_order_instructor})
            return "failed"
        if not ok and not result.get("committed"):
            logger.error(f"✗ {product_code} was not assigned from the Code Blue account (stopped before Confirm)")
            return "failed"
        logger.error(f"? {product_code}: could not confirm the Code Blue assignment "
                     f"(success={ok}, stock {before} -> {after})")
        return "unverified"

    def assign_line(self, order: Dict[str, Any], training_site: str, code_blue: bool = False) -> str:
        """
        Assign one order line on eCards and validate it.
        Returns 'done', 'failed' (nothing was issued) or 'unverified' (eCards may have
        issued cards but we could not confirm it).
        """
        product_code = order.get('product_code', '')
        course_name = order.get('course_name', '')
        name = order.get('name', '')
        quantity = int(order.get('quantity', 0))

        # Code Blue orders (ACLS/PALS keep using the Admin Instructor flow below)
        if code_blue and not is_acls_pals_course(course_name):
            return self.assign_line_code_blue(order)

        # ACLS/PALS go to the Admin Instructor; that flow has its own stock count,
        # so the validation is eCards' confirmation page (checked in finish_assignment)
        if is_acls_pals_course(course_name):
            logger.info(f"ACLS/PALS course {product_code} ({course_name}) assigned to Admin Instructor")
            if assign_to_admin_instructor(self.driver, name, str(quantity), product_code):
                self.stock_info[product_code] = self.stock_info.get(product_code, 0) - quantity
                return "done"
            return "failed"

        # Live stock before assigning
        before = get_inventory_quantity(self.driver, product_code)
        if before is None:
            logger.error(f"Could not read eCards stock for {product_code}")
            return "failed"
        if before < quantity:
            logger.error(f"Live stock for {product_code} is {before}, need {quantity}")
            quantity_required.append({"sku": product_code, "qty": quantity - before, "required_qty": quantity,
                                      "available_qty": before, "order_name": self.current_order_name,
                                      "training_site": self.current_order_site,
                                      "instructor": self.current_order_instructor})
            return "failed"

        # Same assignment rules as before
        if self.available_courses.is_individual_course(product_code) and not training_site.startswith("TS"):
            logger.info(f"Individual course {product_code} assigned to instructor")
            ok = assign_to_instructor(self.driver, name, str(quantity), product_code)
        else:
            site_name = get_training_site_name_for_order(training_site)
            logger.info(f"Course {product_code} assigned to training site {site_name}")
            ok = assign_to_training_center(self.driver, name, str(quantity), product_code, site_name)

        # Validate: live stock must have dropped by exactly the quantity
        after = get_inventory_quantity(self.driver, product_code)
        if after is not None:
            self.stock_info[product_code] = after

        if ok and after is not None and before - after == quantity:
            logger.info(f"✓ Validated {product_code}: stock {before} -> {after}")
            return "done"
        if not ok and after == before:
            logger.error(f"✗ {product_code} was not assigned (stock unchanged at {before})")
            return "failed"
        logger.error(f"? {product_code}: could not confirm the assignment (success={ok}, stock {before} -> {after})")
        return "unverified"

    def process_order(self, order_link: str) -> str:
        """Phase 3: process one order. Returns completed / skipped / short / failed / review / dry-run."""
        order_id = get_order_id(order_link)
        order_name = f"CB-{order_id}"

        # 7. Open the order on Enroll Nationwide
        self.switch_to(self.enw_tab)
        if not safe_navigate_to_url(self.driver, order_link):
            logger.error(f"{order_name}: could not open the order")
            return "failed"

        # 8. Collect the order data
        order_data, _ = get_order_data(self.driver)
        if not order_data:
            logger.warning(f"{order_name}: no order data found")
            return "failed"

        # Orders that show a "Certificates" section are skipped
        if self.driver.find_elements(*EnrollNationwideOrderPage.certificates_heading):
            logger.info(f"{order_name}: 'Certificates' section found on the order page, skipping")
            self.skip_reason = "Certificates section on the order page"
            return "skipped"

        status, payment = get_order_status(self.driver)
        if status not in STATUSES_TO_PROCESS:
            logger.info(f"{order_name}: status is '{status}', nothing to do")
            self.skip_reason = f"status is '{status}'"
            return "skipped"
        if payment != "paid":
            # not recorded: the order can still be paid later
            logger.info(f"{order_name}: payment status is '{payment}', will check again next run")
            return "waiting"

        # Training site on the order page: Code Blue CPR Services -> assign from the Code Blue account
        self.current_order_name = order_name
        site_elements = self.driver.find_elements(*EnrollNationwideOrderPage.training_site_name)
        page_training_site = (site_elements[0].get_attribute("textContent") or "").strip() if site_elements else ""
        order_site = order_data[0].get('training_site', '')
        code_blue = (CODE_BLUE_SITE_TEXT in page_training_site.lower()
                     or order_site.upper().startswith(CODE_BLUE_SITE_CODE))
        if code_blue:
            logger.info(f"{order_name}: Code Blue CPR Services order (training site '{page_training_site or order_site}')")

        name = order_data[0].get('name', '')
        training_site = order_data[0].get('training_site', '')
        self.current_order_site = training_site or page_training_site
        self.current_order_instructor = name
        logger.info(f"{order_name}: {name} - Training Site: {training_site or '-'}")
        for i, order in enumerate(order_data, 1):
            logger.info(f"  {i}. {order.get('quantity')} {order.get('product_code') or '(no SKU)'} {order.get('course_name')}")

        ecard_lines = list(enumerate(order_data))

        # Check if any course should be skipped (whole order is left for a person)
        for _, order in ecard_lines:
            should_skip, skip_reason = self.should_skip_course(order.get('course_name', ''), order.get('product_code', ''))
            if should_skip:
                logger.info(f"{order_name}: skipping entire order due to: {skip_reason}")
                self.skip_reason = skip_reason
                return "skipped"

        # Lines already issued in an earlier run (order stopped halfway) are not issued again
        pending_lines = []
        for idx, order in ecard_lines:
            key = OrderLedger.item_key(idx, order['product_code'])
            line_status = self.ledger.item_status(order_id, key)
            if line_status == "unverified":
                needs_review.append(f"{order_name} – {order['product_code']} x{order['quantity']} for {name}: "
                                    f"check eCards, then complete the order by hand")
                return "review"
            if line_status != "done":
                pending_lines.append((idx, key, order))

        # Lines already moved to the Code Blue site in an earlier run don't need main-account stock
        needs_main_stock = [order for _, key, order in pending_lines
                            if self.ledger.item_status(order_id, key) != "transferred"]
        if not self.reserve_order_stock(needs_main_stock, order_name):
            return "short"

        if DRY_RUN:
            for _, _, order in pending_lines:
                source = f" via {CODE_BLUE_ECARDS_SITE} and the Code Blue account" if code_blue else ""
                logger.info(f"[DRY RUN] would assign {order['quantity']} x {order['product_code']} to {name}{source}")
                self.stock_info[order['product_code']] = self.stock_info.get(order['product_code'], 0) - int(order['quantity'])
            logger.info(f"[DRY RUN] would mark {order_name} as Completed")
            return "dry-run"

        # 9–10. Navigate to eCards and process each line, validating as we go
        if pending_lines:
            if not self.setup_eCards_session():
                return "failed"
            for idx, key, order in pending_lines:
                if self.ledger.item_status(order_id, key) == "transferred":
                    result = self.assign_line_from_code_blue(order)
                else:
                    result = self.assign_line(order, training_site, code_blue)
                if result == "transferred":
                    self.ledger.mark_item(order_id, key, order['product_code'], int(order['quantity']), "transferred")
                    logger.error(f"{order_name}: order left open; the Code Blue step will be retried next run")
                    return "failed"
                if result in ("done", "unverified"):
                    self.ledger.mark_item(order_id, key, order['product_code'], int(order['quantity']), result)
                if result == "unverified":
                    needs_review.append(f"{order_name} – {order['product_code']} x{order['quantity']} for {name}: "
                                        f"assignment could not be confirmed")
                    return "review"
                if result != "done":
                    logger.error(f"{order_name}: {order['product_code']} failed – order left open")
                    return "failed"

        # 11–12. Back to Enroll Nationwide (order still open in its tab) and mark it Completed
        self.switch_to(self.enw_tab)
        if mark_order_as_complete(self.driver, order_link):
            self.ledger.clear(order_id)
            logger.info(f"✓ {order_name} completed")
            return "completed"
        logger.error(f"{order_name}: eCards assigned but the order could not be marked Completed "
                     f"(next run will retry without assigning again)")
        return "failed"

    def print_summary(self):
        print(f"\n{'=' * 50}\nPROCESSING SUMMARY{' (DRY RUN)' if DRY_RUN else ''}\n{'=' * 50}")
        for key in ("completed", "dry-run", "short", "review", "failed", "skipped", "waiting"):
            if self.results.get(key):
                print(f"{key.title():<10} {len(self.results[key]):>3}  {', '.join(self.results[key])}")
        if not any(self.results.values()):
            print("No orders to process")
        print("=" * 50)


def main():
    logger.info("Starting automation process...")
    if not validate_environment_variables():
        logger.error("Fix the .env file and restart")
        return

    processor = OrderProcessor()
    if not processor.initialize():
        logger.error("Failed to initialize order processor")
        return

    try:
        # Phase 1: stock check on eCards
        logger.info("PHASE 1 - Capturing eCards stock...")
        if not processor.refresh_stock_snapshot():
            logger.error("Could not capture eCards stock snapshot; stopping this run")
            return

        # Phase 2: orders to process on Enroll Nationwide
        logger.info("PHASE 2 - Logging into EnrollNationwide and collecting orders...")
        order_links = processor.get_orders()
        if order_links is None:
            logger.error("Failed to login to EnrollNationwide")
            return
        processor.ledger.prune([get_order_id(link) for link in order_links])

        # Orders already completed or skipped in an earlier run are not opened again
        already_done = [link for link in order_links if processor.processed_orders.is_processed(get_order_id(link))]
        if already_done:
            logger.info(f"Ignoring {len(already_done)} order(s) already completed/skipped in earlier runs: "
                        f"{['CB-' + get_order_id(link) for link in already_done]}")
        order_links = [link for link in order_links if link not in already_done]

        if not order_links:
            logger.info("No new orders to process")
            return

        # Phase 3: one order at a time
        logger.info(f"PHASE 3 - Processing {len(order_links)} order(s)...")
        for i, order_link in enumerate(order_links, 1):
            order_id = get_order_id(order_link)
            order_name = f"CB-{order_id}"
            logger.info(f"[{i}/{len(order_links)}] Processing order {order_name}")
            processor.skip_reason = ""
            try:
                outcome = processor.process_order(order_link)
            except Exception as e:
                logger.error(f"Unexpected error processing {order_name}: {e}")
                outcome = "failed"
            processor.results.setdefault(outcome, []).append(order_name)

            # Remember finished orders so later runs don't open them again.
            # failed / short / review / waiting orders are retried on the next run.
            if outcome in ("completed", "skipped") and not DRY_RUN:
                processor.processed_orders.record(order_id, outcome, processor.skip_reason)

        processor.print_summary()

    except Exception as e:
        logger.error(f"Critical error in main process: {e}")
    finally:
        # Phase 4: close the driver
        processor.cleanup()


def send_stock_notification():
    """Phase 4: Discord message for stock shortages (and orders that need a manual check)."""
    global last_message
    message = generate_stock_message(quantity_required, needs_review)
    if not message:
        logger.info("No stock shortages found")
        return
    if DRY_RUN:
        logger.info(f"[DRY RUN] Discord message would be:\n{message}")
        return
    if message == last_message:
        logger.info("Same shortages as the last run; Discord message not repeated")
        return
    if DiscordNotifier(os.getenv("DISCORD_WEBHOOK_URL")).send_notification(message):
        logger.info("Discord notification sent for inventory replenishment")
        last_message = message


SCHEDULE_INTERVAL_SECONDS = 15 * 60  # 15 minutes

def run_every_15_minutes():
    logger.info("Starting scheduled automation (runs every 15 minutes)")
    run_count = 0

    while True:
        run_count += 1
        global quantity_required, needs_review
        quantity_required = []
        needs_review = []
        start = time.time()
        print(f"\n{'='*50}")
        print(f"SCHEDULED RUN #{run_count}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*50}")

        try:
            main()
            send_stock_notification()
        except Exception as e:
            logger.error(f"Unhandled error in scheduled run #{run_count}: {e}")

        # Phase 4: wait for the next scheduled run
        elapsed = time.time() - start
        remaining = SCHEDULE_INTERVAL_SECONDS - elapsed

        if remaining > 0:
            next_run_time = datetime.fromtimestamp(time.time() + remaining).strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Run #{run_count} completed in {elapsed:.1f}s")
            logger.info(f"Next run scheduled for: {next_run_time}")
            logger.info(f"Waiting {remaining/60:.1f} minutes...")
            time.sleep(remaining)
        else:
            logger.info(f"Run #{run_count} took {elapsed:.1f}s (>= 15 minutes). Starting next run immediately.")


if __name__ == "__main__":
    try:
        run_every_15_minutes()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user (Ctrl+C)")
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error in main application: {e}")
    finally:
        print("Application shutting down...")
        logger.info("Application shutdown complete")
