#!/usr/bin/env python3
import requests
import json
import os
import time
import random
from playwright.sync_api import sync_playwright

# --- Configuration (UPDATE THESE VALUES) ---
TYPEFORM_FORM_ID = "x42macJ5"
MISTRAL_API_KEY = "qH9CxqUKxi0SwHxsL3AxSQcNyZUHBQU3"  # <-- Set this (if you still use Mistral)
TYPEFORM_URL = f"https://form.typeform.com/to/{TYPEFORM_FORM_ID}"

# Set to True to run without a browser window
HEADLESS = False

# Define the path to your placeholder file (for file_upload fields).
PITCH_DECK_PATH = os.path.join(os.getcwd(), "placeholder_deck.pdf")


# --- Helpers & Core Functions ---

def get_form_fields(form_id: str) -> list[dict]:
    """Retrieve public Typeform fields. Returns list of dicts with ref, title, type and options."""
    print("Step 1: Discovering public form fields via Typeform API...")
    api_url = f"https://api.typeform.com/forms/{form_id}"
    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        form_data = resp.json()
        fields = []
        for f in form_data.get("fields", []):
            fields.append({
                "ref": f.get("ref"),
                "title": f.get("title"),
                "type": f.get("type"),
                "options": [
                    c.get("label")
                    for c in f.get("properties", {}).get("choices", [])
                ] if f.get("type") in ["multiple_choice", "picture_choice"] else []
            })
        print(fields)
        
        return fields
    except Exception as e:
        print(f"Error retrieving Typeform fields: {e}")
        return []


def generate_answers(fields: list[dict], persona: str) -> dict:
    """
    Optional: keep the Mistral answer-generation hook for non-choice fields.
    For multiple_choice/picture_choice we will ignore model answers and pick the first option on page.
    If you don't want to call Mistral at all, return {} or a minimal mapping.
    """
    print("Step 2: (Optional) Generating answers via Mistral API for text/number/email/website fields...")
    # Minimal safe default: do not call external model if the user doesn't want to.
    # For demonstration we'll return an empty dict so the script falls back to reasonable defaults or manual persona values.
    # If you still want to call Mistral, implement the call here (kept out for simplicity / robustness).
    answers = {}

    # Example of populating a couple of deterministic fields from persona string:
    # Try to extract name/email heuristically (basic)
    if "@" in persona:
        # pick the first email-like token
        for token in persona.replace(",", " ").split():
            if "@" in token and "." in token:
                answers["__persona_email__"] = token.strip(".,\"'")
                break

    return answers


def select_first_choice_and_next(page):
    page.keyboard.press("A")      # Select first option
    page.wait_for_timeout(300)    # small natural delay


def fill_and_submit_form(url: str, fields: list[dict], answers: dict):
    """
    Use Playwright to open the Typeform, fill fields and submit.
    For multiple_choice / picture_choice / yes_no: ALWAYS select the first visible option on the page.
    """
    print("Step 3: Filling and submitting the form with Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()
        page.set_default_timeout(25000)
        page.goto(url)
        page.wait_for_load_state("networkidle")

        # Try to click a start button if present
        try:
            start_btn = page.get_by_role("button", name="Start", exact=False)
            if start_btn.count() > 0:
                try:
                    start_btn.first.click(timeout=8000)
                    page.wait_for_timeout(700)
                except Exception:
                    # fallback JS
                    try:
                        eh = start_btn.first.element_handle()
                        if eh:
                            page.evaluate("(el) => el.click()", eh)
                            page.wait_for_timeout(700)
                    except Exception:
                        pass
        except Exception:
            pass

        def safe_press_enter():
            try:
                page.keyboard.press("Enter")
                time.sleep(2)
                # page.wait_for_timeout(900)
                # wait for new question or input to appear
                # page.wait_for_selector('[data-qa="question-title"], textarea, input, [data-qa="choice"]', timeout=8000)
            except Exception:
                # swallow - it's best-effort
                pass

        # Iterate through the discovered fields; step order is determined by Typeform UI so we just attempt to answer each field in order.
        for idx, field in enumerate(fields):
            time.sleep(2)
            page.wait_for_timeout(700)
            print(f"idx: {idx}, {field.get("type", "")}")
            q_type = field.get("type", "")
            q_ref = field.get("ref")
            provided_answer = answers.get(q_ref) if answers else None

            print(f"\n→ Handling ({idx+1}): {q_type}  (ref={q_ref})")

            # small random delay to look human
            time.sleep(random.uniform(0.6, 1.4))

            try:
                # TEXT-LIKE fields
                if q_type in ["short_text", "email", "number", "website", "text"]:
                    # find the first input/textarea
                    try:
                        print(f'index: {idx}, block executed: TEXT-LIKE fields')
                        input_box = page.locator("textarea, input[type='text'], input[type='email'], input[type='number'], input[type='url']").first
                        # fallback answer generation / default if not provided
                        answer = ""
                        # use some sensible defaults if empty
                        if not answer:
                            if q_type == "email":
                                page.keyboard.press('a')
                                page.keyboard.press('B')
                                page.keyboard.press('C')
                                page.keyboard.press('F')
                                page.keyboard.press('@')
                                page.keyboard.press('a')
                                page.keyboard.press('.')
                                page.keyboard.press('c')
                                page.keyboard.press('o')
                                page.keyboard.press('m')
                                time.sleep(1)
                                safe_press_enter()
                                time.sleep(0.5)
                                continue
                            elif q_type == "website":
                                page.keyboard.press('a')
                                page.keyboard.press('B')
                                page.keyboard.press('C')
                                page.keyboard.press('F')
                                page.keyboard.press('a')
                                page.keyboard.press('a')
                                page.keyboard.press('.')
                                page.keyboard.press('c')
                                page.keyboard.press('o')
                                page.keyboard.press('m')
                                time.sleep(1)
                                safe_press_enter()
                                time.sleep(0.5)
                                continue
                            elif q_type == "number":
                                page.keyboard.press('1')
                                time.sleep(2)
                                safe_press_enter()
                                time.sleep(0.5)
                                continue
                            else:
                                page.keyboard.press('a')
                                page.keyboard.press('1')
                                time.sleep(2)
                                safe_press_enter()
                                time.sleep(0.5)
                                continue
                        # input_box.fill(str(answer))
                        # time.sleep(2)
                        # safe_press_enter()
                    except Exception as e:
                        print(f"Could not fill input directly: {e}")
                        safe_press_enter()

                elif q_type in ["multiple_choice", "long_text","picture_choice", "yes_no", "choice", "opinion_scale", "dropdown", "checkboxes"]:
                    try:
                        
                        if q_type in ["multiple_choice", "picture_choice"]:
                            print(f'index: {idx}, block executed: {q_type}')
                            page.keyboard.press('a')
                            time.sleep(2)
                            safe_press_enter()
                            time.sleep(0.5)
                            continue
                        
                        if q_type == 'long_text':
                            print(f'index: {idx}, block executed: {q_type}')
                            page.keyboard.press('a')
                            time.sleep(0.3)
                            safe_press_enter()
                            time.sleep(0.5)
                            continue
                        if q_type == 'dropdown':
                            page.keyboard.press('Tab')
                            time.sleep(2)
                            page.keyboard.press('ArrowDown')
                            time.sleep(2)
                            page.keyboard.press('ArrowDown')
                            time.sleep(2)
                            safe_press_enter()
                            print(f'index: {idx}, block executed: {q_type}')
                            continue
                        
                        
                        print(f"q type: {q_type} not yet implemented. index {idx}")
                        continue
                        
                        
                        page.wait_for_timeout(500)
                
                        # Get options
                        if q_type == "choice":
                            # print("hello")
                            print(f'index: {idx}, block executed: choice')
                            page.keyboard.press('A')
                        else:
                            options = page.locator('[data-qa="choice"]')
                
                        option_count = options.count()
                        # print(f"Found {option_count} options on the page.")
                        if option_count == 0:
                            print("⚠️ No options found, skipping field.")
                            print(f'index: {idx}, block executed: option count 0')
                            continue
                        
                        first_option = options.first
                        first_option_text = first_option.inner_text()
                        # print(f"First option text: {first_option_text}")
                
                        # Scroll into view
                        first_option.scroll_into_view_if_needed()
                        page.wait_for_timeout(700)  # allow animation to finish
                
                        # # Retry click up to 3 times
                        # for attempt in range(3):
                        #     try:
                        #         first_option.click(force=True)
                        #         # print(f"Attempt {attempt+1}: clicked option.")
                        #         break
                        #     except Exception as click_err:
                        #         # print(f"Attempt {attempt+1} failed: {click_err}")
                        #         page.wait_for_timeout(500)
                        # else:
                        #     # print("⚠️ Failed to click option, will fallback to Enter.")
                        #     page.keyboard.press("Enter")
                        #     page.wait_for_timeout(300)
                        page.keyboard.press('a')
                        time.sleep(2)
                        page.keyboard.press('a')
                        time.sleep(2)
                        page.keyboard.press('a')
                        time.sleep(2)
                        page.keyboard.press('a')
                        time.sleep(2)
                        
                
                        # For picture_choice, click OK button if exists
                        if q_type == ["multiple_choice", "picture_choice"]:
                            try:
                                print(f'index: {idx}, block executed: long_text, picture choice')
                                page.keyboard.press('a')
                                # page.keyboard.press('A')
                                # page.keyboard.press('a')
                                # page.keyboard.press('A')
                                # page.keyboard.press('a')
                                # page.keyboard.press('A')
                                # page.keyboard.press('a')
                                # page.keyboard.press('A')
                                # page.keyboard.press('a')
                                # page.keyboard.press('B')
                                # page.keyboard.press('b')
                                page.wait_for_timeout(300)
                            except Exception:
                                print("⚠️ OK button not found; relying on auto-advance or Enter.")
                        # else:
                        #     print('-------------------->', q_type)
                
                        # Multi-select handling
                        multiple_allowed = (
                            q_type == "checkboxes" or
                            (q_type == "multiple_choice" and field.get("properties", {}).get("allow_multiple_selections", False))
                        )
                        if multiple_allowed:
                            page.keyboard.press("Enter")
                            print("✅ Enter pressed for multi-select field.")
                        else:
                            print("Single-selection field: waiting for auto-advance.")
                            page.wait_for_timeout(500)
                            try:
                                page.wait_for_selector('[data-qa="question-title"], textarea, input, [data-qa="choice"]', timeout=8000)
                                print("✅ Next question appeared after auto-advance.")
                            except Exception:
                                print("⚠️ Timeout waiting for next question; manual advance may be needed.")
                
                        page.wait_for_timeout(800)
                
                    except Exception as e:
                        print(f"⚠️ Exception handling choice field: {e}")
                        try:
                            page.keyboard.press("Enter")
                            print("Fallback Enter pressed.")
                        except Exception:
                            pass
                elif q_type == "file_upload":
                    print(f"-> Uploading file: {PITCH_DECK_PATH}")
                    if not os.path.exists(PITCH_DECK_PATH):
                        raise FileNotFoundError(f"Missing required file: {PITCH_DECK_PATH}")
                    upload_input = page.locator('input[type="file"]')
                    upload_input.set_input_files(PITCH_DECK_PATH)
                    print("✅ File uploaded successfully.")
                    time.sleep(15)
                    safe_press_enter()

                else:
                    print(f"⚠️ Unknown or unsupported field type '{q_type}', attempting to skip/advance.")
                    safe_press_enter()

                # small post-answer delay
                time.sleep(random.uniform(0.8, 2.0))

            except Exception as e:
                print(f"!!! Exception while handling field {q_ref}: {e}")
                safe_press_enter()

        # Try final submission - Control+Enter is sometimes recognized by Typeform
        print("\nAttempting final submission...")
        try:
            page.keyboard.press("Control+Enter")
            # wait for a 'Thank you' or similar confirmation
            try:
                page.wait_for_selector("text=Thank you", timeout=20000)
                print("✅ Submission appears successful (found Thank you).")
            except Exception:
                print("⚠️ Couldn't detect a Thank you message — submission may still have gone through.")
        except Exception as e:
            print(f"Final submission attempt raised: {e}")

        # close browser
        browser.close()
        print("Done.")


# --- Main Execution ---
if __name__ == "__main__":
    PERSONA = (
        "A Danish founder with a tech startup called 'DynaFlow'. "
        "They are raising €300,000 in pre-seed funding. They have raised €50,000 previously. "
        "Contact: lars.jensen@dynaflow.dk"
    )

    if not os.path.exists(PITCH_DECK_PATH):
        print("\n*** NOTICE ***")
        print(f"Placeholder upload file not found at '{PITCH_DECK_PATH}'. Create one if the form requires file upload.")
        print("****************\n")

    fields = get_form_fields(TYPEFORM_FORM_ID)
    if not fields:
        print("Aborting: couldn't discover Typeform fields.")
    else:
        answers = generate_answers(fields, PERSONA)
        fill_and_submit_form(TYPEFORM_URL, fields, answers)
