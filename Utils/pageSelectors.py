from selenium.webdriver.common.by import By


BASE_URL = "https://enrollnationwide.com"


def xpath_literal(value) -> str:
    """Safely quote a value for use inside an XPath expression.

    Names like O'Brien or emails like o'neil@x.com would otherwise break
    a selector written as text()= '{x}'.
    """
    value = "" if value is None else str(value)
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


_q = xpath_literal


class QuickLinks:
    login_page = f"{BASE_URL}/login"
    dashboard = f"{BASE_URL}/account/"
    aha_orders = f"{BASE_URL}/account/?view=manage&tab=orders&org=aha"
    # Orders list filtered by status: new / viewed / pending / completed
    aha_orders_by_status = lambda status: f"{BASE_URL}/account/?view=manage&tab=orders&org=aha&os={status}"
    order_page = lambda order_id: f"{BASE_URL}/account/?view=manage&tab=orders&sub=orders&order={order_id}"
    ecards_inventory = "https://ecards.heart.org/inventory"
    ecards_instructor_assignment = "https://ecards.heart.org/InstructorAssignment"

class EnrollNationwideLoginPage:
    username_input = (By.CSS_SELECTOR, "#email")
    password_input = (By.CSS_SELECTOR, "#password")
    remember_me_checkbox = (By.CSS_SELECTOR, "#remember_me")
    login_button = (By.XPATH, "//button[text()= 'Login']")
    info_needed_popup = (By.XPATH, "//a[text()= 'Fill out later']")

class EnrollNationwideOrdersList:
    order_rows = (By.XPATH, "//a[@role='row' and contains(@href, 'order=')]")
    # inside a row: 5th column holds the badges -> [provider, order status, payment status]
    row_status = (By.XPATH, "./span[5]/span[2]")
    row_payment = (By.XPATH, "./span[5]/span[3]")
    row_order_number = (By.XPATH, "./span[1]//strong")
    next_page_link = (By.XPATH, "//a[contains(@href, 'opg=') and starts-with(normalize-space(.), 'Next')]")

class EnrollNationwideOrderPage:
    order_details = (By.CSS_SELECTOR, "article.cbp-cs-detail")
    # orders with a "Certificates" section are skipped
    certificates_heading = (By.XPATH, "//h2[contains(text(), 'Certificates')]")
    ordered_by_box = (By.XPATH, "//article[contains(@class, 'cbp-cs-detail')]//h3[text()= 'Ordered by' or text()= 'Instructor']/parent::div")
    ordered_by_names = (By.XPATH, "./p/strong")
    # rows of the items grid, header and total rows have extra classes
    ordered_products = (By.XPATH, "//div[@class= 'cbp-cs-itr']")
    checked_status = (By.CSS_SELECTOR, "form.cbp-cs-update input[name='status']:checked")
    payment_status_select = (By.CSS_SELECTOR, "form.cbp-cs-update select[name='pay_status']")
    complete_order_button = (By.XPATH, "//span[text()= 'Completed']")
    message_input = (By.ID, "cbp-cs-msg")
    status_update_button = (By.XPATH, "//button[contains(text(), 'Update & send email')]")

class AHALoginPage:
    sign_in_link = (By.XPATH, "(//button[text()= 'Sign In | Sign Up'])[1]")
    username_input = (By.ID, "Email")
    password_input = (By.ID, "Password")
    sign_in_button = (By.ID, "btnSignIn")

class AHAInventoryPage:
    maintenance_message = (By.XPATH, "//span[contains(text(), 'Our site will be under maintenance')]")
    # any visible error eCards shows after Confirm / Complete
    error_messages = (By.CSS_SELECTOR, ".validation-summary-errors, .field-validation-error, .alert-danger, .toast-error")
    stock_id = lambda x: (By.XPATH, f"//tbody/tr[@role='row']/td[{x}]")
    available_course_selector = lambda x: f"//td[contains(text(), '{x}')]/preceding-sibling::td"
    assign_to = lambda x: (By.XPATH, f"//div/a[contains(text(), 'Assign to {x}')]")
    finish_button = (By.ID, "btnComplete")
    go_to_inventory_button = (By.XPATH, "//a[text()= 'Go To Inventory']")

class AssignToInstructorPage:
    role_select = (By.ID, "RoleId")
    course_select = (By.ID, "CourseId")
    training_center_select = (By.ID, "ddlTC")
    training_site_select = (By.ID, "ddlSite")
    instructor_select = (By.XPATH, "//select[@id= 'assignTo']/following-sibling::div/button")
    instructor_name_selector = lambda x: (By.XPATH, f"(//label[contains(text(), '{x}')])[1]")
    submit_button = (By.ID, "btnMoveNext")
    quantity_input = (By.ID, "qty1")
    available_quantity = (By.ID, "tdAvailQty")
    continue_button = (By.ID, "btnConfirm")

class AssignToTrainingCenterPage:
    training_center_select = (By.ID, "tcId")
    training_site_select = (By.ID, "tsList")
    course_select = (By.ID, "courseId")
    submit_button = (By.ID, "btnValidate")
    quantity_input = (By.ID, "qty")
