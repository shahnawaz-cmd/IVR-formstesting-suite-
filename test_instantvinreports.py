import csv
import os
import platform
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL = "https://instantvinreports.com/"
REPORT_DIR = Path("test_results")
SCREENSHOT_DIR = REPORT_DIR / "screenshots"
HTML_REPORT = REPORT_DIR / "instantvinreports_test_report.html"
ZIP_NAME = Path("instantvinreports_test_results.zip")
FORM_XPATH = "/html/body/main/div/div[1]/div/div/div[1]/div[3]"


def ensure_report_dir():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(value):
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', value)
    sanitized = sanitized.strip().replace(' ', '_')
    return sanitized


def save_screenshot_for_test(driver, test_name, status):
    filename = f"{sanitize_filename(test_name)}_{status}.png"
    filepath = SCREENSHOT_DIR / filename
    try:
        driver.save_screenshot(str(filepath))
        return filepath
    except Exception:
        return None


def write_html_report(results):
    rows = []
    for result in results:
        actions = result.get('actions', [])
        actions_html = "<br>".join(actions)
        screenshot_html = "-"
        screenshot = result.get('screenshot')
        if screenshot:
            filename = screenshot.name
            screenshot_html = (
                f"<a href='screenshots/{filename}' target='_blank' title='Open screenshot in new tab'>"
                f"<img src='screenshots/{filename}' alt='{filename}' title='{filename}' style='max-width:160px; max-height:120px; display:block; border:1px solid #999; margin-bottom:4px;'/>"
                f"</a>"
                f"<div style='font-size:0.8em; color:#333;'>{filename}</div>"
            )
        row_class = "pass" if result['status'].lower() == "pass" else "fail"
        rows.append(
            f"<tr class='{row_class}'>"
            f"<td>{result['test_name']}</td>"
            f"<td>{result['input']}</td>"
            f"<td>{result['expected']}</td>"
            f"<td>{result['actual']}</td>"
            f"<td>{result['status']}</td>"
            f"<td>{result['notes']}</td>"
            f"<td>{screenshot_html}</td>"
            f"<td>{actions_html}</td>"
            f"</tr>"
        )

    html = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\">
<title>InstantVINReports Selenium Test Report</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
  th {{ background: #f5f5f5; }}
  .pass {{ background: #d4edda; }}
  .fail {{ background: #f8d7da; }}
  .pass td {{ background: #d4edda; }}
  .fail td {{ background: #f8d7da; }}
  a {{ color: #155724; }}
</style>
</head>
<body>
  <h1>InstantVINReports Selenium Test Report</h1>
  <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
  <table>
    <thead>
      <tr>
        <th>Test</th>
        <th>Input</th>
        <th>Expected</th>
        <th>Actual</th>
        <th>Status</th>
        <th>Notes</th>
        <th>Screenshot</th>
        <th>Action Log</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    HTML_REPORT.write_text(html, encoding="utf-8")


def zip_report():
    with zipfile.ZipFile(ZIP_NAME, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(HTML_REPORT, HTML_REPORT.name)


def find_clickable(driver, by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))


def find_visible(driver, by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, value)))


def safe_get_text(element):
    return element.text.strip() if element else ""


def record_action(action_list, message):
    if action_list is not None:
        action_list.append(message)


def get_form_root(driver, results=None):
    form_root = None
    try:
        form_root = driver.find_element(By.XPATH, FORM_XPATH)
    except NoSuchElementException:
        try:
            form_root = driver.find_element(By.CSS_SELECTOR, "section.site_form")
        except NoSuchElementException:
            form_root = None

    return form_root


def switch_to_tab(root_element, tab_name):
    if root_element is None:
        return False
    tab_name_lower = tab_name.lower()
    target_text = "by us license plate" if "lp" in tab_name_lower or "license" in tab_name_lower else "by vin"
    xpath = ".//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '" + target_text + "')]"
    buttons = root_element.find_elements(By.XPATH, xpath)
    if not buttons:
        return False
    buttons[0].click()
    time.sleep(1)
    return True


def get_page_url(driver):
    return driver.current_url


def interact_with_plan_radio(driver, action_log, section_xpath="/html/body/div[4]/div/div/div/div[2]/div"):
    record_action(action_log, f"Looking for plan section using XPath: {section_xpath}")
    try:
        section = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.XPATH, section_xpath)))
    except Exception as exc:
        record_action(action_log, f"Failed to locate plan section: {exc}")
        return False

    try:
        heading = section.find_element(By.XPATH, ".//h4[contains(normalize-space(.), 'Unlock the history - Choose your package.')]")
        record_action(action_log, f"Found plan heading: {heading.text.strip()}")
    except NoSuchElementException:
        record_action(action_log, "Plan heading not found in plan section")
        return False

    radio_buttons = section.find_elements(By.XPATH, ".//input[@type='radio']")
    if not radio_buttons:
        record_action(action_log, "No plan radio buttons found under the plan section")
        return False

    interacted = 0
    for idx, radio_button in enumerate(radio_buttons, start=1):
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", radio_button)
            time.sleep(0.5)
            try:
                radio_button.click()
            except Exception:
                driver.execute_script("arguments[0].click();", radio_button)
            record_action(action_log, f"Clicked plan radio {idx}/{len(radio_buttons)}")
            try:
                plan_label = radio_button.find_element(By.XPATH, "ancestor::label[1]").text.strip()
                record_action(action_log, f"Plan label text: {plan_label}")
            except Exception:
                pass
            time.sleep(2)
            interacted += 1
        except Exception as exc:
            record_action(action_log, f"Failed to interact with plan radio {idx}: {exc}")

    if interacted == len(radio_buttons):
        record_action(action_log, f"Interacted with all {len(radio_buttons)} plan radios")
        return True

    record_action(action_log, f"Interacted with {interacted}/{len(radio_buttons)} plan radios")
    return False


def select_state_with_retry(driver, action_log, state_select, state_value):
    record_action(action_log, f"Selecting state: {state_value}")
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                record_action(action_log, f"Attempt {attempt} to open state dropdown and select {state_value}")
            try:
                state_select.click()
            except ElementClickInterceptedException as exc:
                record_action(action_log, f"State dropdown click intercepted: {exc}, using JS click")
                driver.execute_script("arguments[0].click();", state_select)
            time.sleep(0.5)

            try:
                select = Select(state_select)
                select.select_by_visible_text(state_value)
                record_action(action_log, f"Successfully selected state by visible text on attempt {attempt}")
                return True
            except Exception as exc_select:
                record_action(action_log, f"Visible text select failed: {exc_select}")

            try:
                driver.execute_script("if(typeof listStateData==='function'){listStateData();}")
                time.sleep(0.5)
                select = Select(state_select)
                for option in select.options:
                    if state_value.lower() in option.text.lower():
                        select.select_by_visible_text(option.text)
                        record_action(action_log, f"Selected state by matching option text: {option.text}")
                        return True
            except Exception as exc_send:
                record_action(action_log, f"Send keys selection attempt failed: {exc_send}")

            try:
                state_select.send_keys(state_value)
                time.sleep(0.5)
                select = Select(state_select)
                for option in select.options:
                    if state_value.lower() in option.text.lower():
                        select.select_by_visible_text(option.text)
                        record_action(action_log, f"Selected state by typing and matching option text: {option.text}")
                        return True
            except Exception as exc_send:
                record_action(action_log, f"Send keys selection attempt failed: {exc_send}")

            try:
                driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change'));",
                    state_select,
                    state_value,
                )
                time.sleep(0.5)
                selected_value = driver.execute_script("return arguments[0].value", state_select)
                if selected_value:
                    record_action(action_log, f"Set state dropdown value via JS to: {selected_value}")
                    return True
            except Exception as exc_js:
                record_action(action_log, f"JS value set failed: {exc_js}")

            raise Exception("Unable to select state value")
        except Exception as exc:
            record_action(action_log, f"Attempt {attempt} failed: {exc}")
            if attempt < attempts:
                time.sleep(0.5)
                continue
            record_action(action_log, "State selection failed after 3 attempts")
            return False


def run_vin_tests(driver, results):
    def execute_vin_test(label, vin_value, expected_url, expect_plan_interaction=False):
        action_log = []
        if driver.current_url != BASE_URL:
            record_action(action_log, "Returning to base page before VIN test")
            driver.get(BASE_URL)
            time.sleep(5)

        form_root = get_form_root(driver)
        if not switch_to_tab(form_root, "By VIN"):
            results.append({
                "test_name": label,
                "input": vin_value,
                "expected": expected_url,
                "actual": "By VIN tab not found",
                "status": "fail",
                "notes": "Cannot switch to By VIN tab.",
                "actions": action_log,
            })
            return

        vin_input = find_visible(driver, By.ID, "vinInput")
        submit_button = find_clickable(driver, By.ID, "site_form_submit")

        status = "fail"
        actual_message = ""
        notes = ""
        current_url = ""
        try:
            record_action(action_log, f"Navigating to By VIN tab")
            record_action(action_log, f"Entering VIN: {vin_value}")
            vin_input.clear()
            vin_input.send_keys(vin_value)
            driver.execute_script("arguments[0].scrollIntoView(true);", vin_input)
            time.sleep(0.5)
            record_action(action_log, "Clicking Search VIN button")
            submit_button.click()
            time.sleep(6)

            current_url = get_page_url(driver)
            try:
                error_element = driver.find_element(By.ID, "errorText_vin")
                actual_message = safe_get_text(error_element)
            except NoSuchElementException:
                actual_message = ""

            if current_url.strip() == expected_url.strip():
                if expect_plan_interaction:
                    record_action(action_log, "Verifying plan radio button interaction after redirect")
                    if interact_with_plan_radio(driver, action_log):
                        status = "pass"
                        notes = f"Redirected to expected VIN preview URL and plan radio interacted: {current_url}"
                        driver.get(BASE_URL)
                        time.sleep(4)
                        record_action(action_log, "Returned to base page after interacting with all plans")
                    else:
                        status = "fail"
                        notes = f"Redirected correctly but plan radio interaction failed on {current_url}"
                else:
                    status = "pass"
                    notes = f"Redirected to expected VIN preview URL: {current_url}"
            else:
                status = "fail"
                if actual_message:
                    notes = f"Expected redirect URL {expected_url} but validation error appeared: {actual_message}"
                else:
                    notes = f"Expected redirect URL {expected_url} but got {current_url}"
        except Exception as exc:
            notes = f"Exception during VIN test: {exc}"
            current_url = driver.current_url if driver else ""
            record_action(action_log, notes)

        screenshot = save_screenshot_for_test(driver, label, status)
        results.append({
            "test_name": label,
            "input": vin_value,
            "expected": expected_url,
            "actual": actual_message or current_url,
            "status": status,
            "notes": notes,
            "actions": action_log,
            "screenshot": screenshot,
        })

    execute_vin_test(
        "VIN 17 chars redirect => success",
        "WBAPH7G50BNM56522",
        "https://instantvinreports.com/vin-check/preview?type=vhr&utm_details=&traffic_source=&vin=WBAPH7G50BNM56522&wpPage=homepage&landing=normal",
        expect_plan_interaction=True
    )
    execute_vin_test(
        "VIN 17 chars SH record => success",
        "1FMCU9J98FUA78638",
        "https://instantvinreports.com/vin-check/preview?type=vhr&utm_details=&traffic_source=&vin=1FMCU9J98FUA78638&wpPage=homepage&landing=normal",
        expect_plan_interaction=True
    )


def run_lp_tests(driver, results):
    form_root = get_form_root(driver, results)
    if not switch_to_tab(form_root, "By LP"):
        results.append({
            "test_name": "By LP tab available",
            "input": "n/a",
            "expected": "Tab visible",
            "actual": "Tab not found",
            "status": "fail",
            "notes": "Cannot switch to By LP tab."
        })
        return

    plate_input = find_visible(driver, By.ID, "plateInput")
    state_select = find_visible(driver, By.ID, "stateList")

    def execute_lp_test(label, plate_value, state_value, expected_text, expect_redirect=False, expected_url=None):
        action_log = []
        record_action(action_log, "Navigating to By LP tab")
        record_action(action_log, f"Entering license plate: {plate_value}")
        plate_input.clear()
        plate_input.send_keys(plate_value)
        driver.execute_script("arguments[0].scrollIntoView(true);", plate_input)
        if state_value is not None:
            if not select_state_with_retry(driver, action_log, state_select, state_value):
                record_action(action_log, "State selection failed after retry")

        time.sleep(0.5)
        record_action(action_log, "Finding Search License Plate button")
        submit_button = driver.find_element(By.XPATH, "//*[@id='site_form_submit']")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
        time.sleep(0.5)
        record_action(action_log, "Clicking Search License Plate button")
        try:
            submit_button.click()
        except ElementClickInterceptedException as exc:
            record_action(action_log, f"Search button click intercepted: {exc}, using JS click")
            driver.execute_script("arguments[0].click();", submit_button)
        except Exception as exc:
            record_action(action_log, f"Search button click failed: {exc}, using JS click")
            driver.execute_script("arguments[0].click();", submit_button)

        if expect_redirect or expected_url:
            try:
                WebDriverWait(driver, 15).until(lambda d: d.current_url != BASE_URL)
            except TimeoutException:
                record_action(action_log, "Timeout waiting for redirect after clicking submit")
        else:
            time.sleep(4)

        current_url = get_page_url(driver)
        actual_message = ""
        status = "fail"
        notes = ""

        try:
            error_element = driver.find_element(By.ID, "errorText_plate")
            actual_message = safe_get_text(error_element)
        except NoSuchElementException:
            actual_message = ""

        if expected_text == "error":
            if actual_message:
                status = "pass"
                notes = "Error message displayed as expected."
            else:
                status = "fail"
                notes = "Expected an error message but none appeared."
        else:
            if actual_message:
                status = "fail"
                notes = f"Unexpected validation error: {actual_message}"
            else:
                if expected_url:
                    if current_url.strip() == expected_url.strip():
                        status = "pass"
                        notes = f"Redirected to expected plate preview URL: {current_url}"
                    else:
                        status = "fail"
                        notes = f"Expected redirect URL {expected_url} but got {current_url}"
                elif expect_redirect and current_url == BASE_URL:
                    status = "fail"
                    notes = "Expected a redirect after successful plate submission."
                else:
                    status = "pass"
                    notes = f"Form submitted without error; current URL: {current_url}"

        screenshot = save_screenshot_for_test(driver, label, status)
        results.append({
            "test_name": label,
            "input": f"plate={plate_value}, state={state_value}",
            "expected": expected_url if expected_url else expected_text,
            "actual": actual_message or current_url,
            "status": status,
            "notes": notes,
            "actions": action_log,
            "screenshot": screenshot,
        })

    execute_lp_test("Plate only => error", "hbl1216", None, "error")
    execute_lp_test(
        "Plate TX valid state with retry => success",
        "hbl1216",
        "TX",
        "success",
        expect_redirect=True,
        expected_url="https://instantvinreports.com/vin-check/license-preview?type=vhr&utm_details=&traffic_source=&vin=dGtlbmw2YVJZNENRTE04cUtLY1pPakdka3RHOGhtTGxFZkhOWTdqTE84OD0=&wpPage=homepage&landing=normal"
    )
    execute_lp_test("Plate NY wrong => error", "HBL1234", "NY", "error")


def create_driver():
    chrome_options = webdriver.ChromeOptions()
    # Disable headless so the browser remains visible.
    chrome_options.add_argument("--start-maximized")
    if platform.system() == "Linux":
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(5)
    return driver


def main():
    ensure_report_dir()
    results = []

    driver = create_driver()
    try:
        driver.get(BASE_URL)
        time.sleep(5)

        run_vin_tests(driver, results)
        driver.get(BASE_URL)
        time.sleep(4)
        run_lp_tests(driver, results)

    except (TimeoutException, Exception) as exc:
        print(f"Execution failed: {exc}")
    finally:
        time.sleep(2)
        driver.quit()

    write_html_report(results)
    zip_report()
    print(f"Report generated: {HTML_REPORT.resolve()}")
    print(f"Zip archive: {ZIP_NAME.resolve()}")


if __name__ == "__main__":
    main()
