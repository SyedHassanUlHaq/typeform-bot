import re
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import os
import openai

# -----------------------------
# 1. Setup Google Sheets
# -----------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_credentials.json", scope)
client = gspread.authorize(creds)

# -----------------------------
# 2. Fetch Company Data
# -----------------------------
company_sheet = client.open_by_key(
    "14cq2CN9Z14roxFwzQYN1thtHiEOPxQsStfJWdosf1-4"
).sheet1
company_values = company_sheet.get_all_values()
company_headers = company_values[0]
company_records = [
    {company_headers[i]: row[i] for i in range(len(company_headers))}
    for row in company_values[1:]
]
# Filter only Webform pitches
company_data = [r for r in company_records if r.get("Pitch type") == "Webform"]

# -----------------------------
# 3. Fetch User/Startup Data (handle duplicate headers)
# -----------------------------
user_sheet = client.open_by_key(
    "14cq2CN9Z14roxFwzQYN1thtHiEOPxQsStfJWdosf1-4"
).get_worksheet(1)
user_values = user_sheet.get_all_values()
user_headers = user_values[0]
user_data = []
for row in user_values[1:]:
    record = {}
    for i, val in enumerate(row):
        key = user_headers[i]
        if user_headers.count(key) > 1:
            # append index for duplicate header
            key = f"{key}_{i}"
        record[key] = val
    user_data.append(record)

# -----------------------------
# 4. Setup OpenAI
# -----------------------------
load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

# -----------------------------
# 5. Helper to clean scraped HTML fields
# -----------------------------
def extract_fields(scrape_data):
    cleaned = []
    tag_pattern = re.compile(r'<(input|textarea|select)([^>]*)>', re.IGNORECASE)
    attr_pattern = re.compile(r'(\w+)="([^"]*)"')

    for result_item in scrape_data.get("data", []):
        for r in result_item.get("results", []):
            html = r.get("html", "")
            for match in tag_pattern.finditer(html):
                tag_type = match.group(1).lower()
                attr_string = match.group(2)
                attributes = dict(attr_pattern.findall(attr_string))
                if attributes.get("type", "").lower() == "hidden":
                    continue
                label = r.get("text", "").strip()
                if label:
                    attributes["label"] = label
                attributes["tag"] = tag_type
                cleaned.append(attributes)
    return cleaned

# -----------------------------
# 6. Process each company
# -----------------------------
for company in company_data:
    pitch_link = company.get("Pitch link")
    if not pitch_link:
        continue

    # Scrape form fields
    scrape_payload = {
        "url": pitch_link,
        "elements": [{"selector": "form"}]
    }
    resp = requests.post(
        "https://production-sfo.browserless.io/scrape?token=2TEHjgEmie0OkpMf1d8e2574f2758648f2b6d1eae601d5a97",
        headers={"Content-Type": "application/json"},
        json=scrape_payload,
        verify=False
    )
    scraped_data = resp.json()
    cleaned_fields = extract_fields(scraped_data)

    # Generate BrowserQL via OpenAI
    prompt = f"""
    You are an AI agent that generates **BrowserQL (BQL)** code for automating form submission on web pages.

    You will receive three JSON inputs:
    1. Number of fields → {json.dumps(cleaned_fields, indent=2)}
    2. Company Data → {json.dumps(company, indent=2)}
    3. User/Startup Data → {json.dumps(user_data, indent=2)}

    ---

    ## 🎯 Objective

    Generate a **BrowserQL mutation** that:
    - Navigates to the provided form URL  
    - Fills out all form fields using the actual data from **User/Startup Data**  
    - Submits the form  
    - Waits for the confirmation or navigation  
    - Blocks nonessential resources for efficiency  
    - Mimics human-like typing behavior  

    ---

    ## 🧠 Rules

    ### 1. Use BrowserQL Syntax
    Follow **BrowserQL**, *not* GraphQL.  
    Use commands like `goto`, `type`, `click`, `waitForSelector`, `reject`.  
    Example:
    goto(url: "https://example.com/form", waitUntil: firstContentfulPaint) {{
    status
    }}

    markdown
    Copy code

    ### 2. Selectors
    Each field’s selector must be built **only** from attributes listed in the JSON:  
    - Allowed attributes: `tag`, `type`, `name`, `id`, `placeholder`, `aria-label`, `role`  
    - Use the form `[attr='value']` for each attribute  
    - Combine multiple attributes in the same selector  
    - Do not use CSS class dot syntax (`.class`)  
    - Do not use extra attributes not present in the JSON  
    - Skip `class` unless it is clearly semantic (e.g., `class='form-email'`)

    ✅ Example:  
    input[type='email'][name='Email'][placeholder='Enter your email']

    yaml
    Copy code

    ❌ Avoid:  
    input.framer-form-input[type='email']

    csharp
    Copy code

    ### 3. Submit Button
    Use this universal selector:
    button[type='submit'], input[type='submit'], div[role='button']

    sql
    Copy code

    ### 4. Use Actual Values
    Do **not** use GraphQL variables like `$Email`.  
    Insert the real values from **User/Startup Data** directly into the query as string literals.

    Example:
    type(
    selector: "input[type='email'][name='Email']",
    text: "alice@innohealth.ai"
    )

    python
    Copy code

    ### 5. Add Human-Like Behavior
    BrowserQL automatically mimics human input.  
    If you want to explicitly enable it, note in the comments that it should run with:
    ?humanlike=true

    csharp
    Copy code
    on the session URL.

    ### 6. Optimize Resource Loading
    Block nonessential resources at the start:
    reject(type: [image, stylesheet, media]) {{
    time
    }}

    csharp
    Copy code

    ### 7. Query Structure
    Follow this structure exactly:

    mutation SubmitForm {{
    reject(type: [image, stylesheet, media]) {{
    time
    }}

    goto(url: "<Pitch Link>", waitUntil: networkIdle) {{
    status
    }}

    waitForSelector(selector: "<first form field selector>", visible: true) {{
    selector
    }}

    fill<FieldName>: type(
    selector: "<selector built from field JSON>",
    text: "<actual value>"
    ) {{
    time
    }}

    ...

    clickSubmit: click(
    selector: "button[type='submit'], input[type='submit'], div[role='button']"
    ) {{
    time
    }}

    waitForNavigation(waitUntil: networkIdle) {{
    status
    }}
    }}

    yaml
    Copy code

    ---

    ## 🧩 Example

    If inputs are:

    **Fields JSON:**
    [
    {{
    "fields": [
    {{
    "type": "email",
    "name": "Email",
    "placeholder": "Enter your email",
    "tag": "input"
    }}
    ]
    }}
    ]

    markdown
    Copy code

    **User/Startup Data:**
    {{
    "Email": "alice@innohealth.ai"
    }}

    markdown
    Copy code

    **Company Data:**
    {{
    "Pitch link": "https://www.climentum.com/contact"
    }}

    lua
    Copy code

    Then your **BrowserQL output must be exactly:**

    mutation SubmitForm {{
    reject(type: [image, stylesheet, media]) {{
    time
    }}

    goto(url: "https://www.climentum.com/contact", waitUntil: networkIdle) {{
    status
    }}

    waitForSelector(selector: "input[type='email'][name='Email'][placeholder='Enter your email']", visible: true) {{
    selector
    }}

    fillEmail: type(
    selector: "input[type='email'][name='Email'][placeholder='Enter your email']",
    text: "alice@innohealth.ai"
    ) {{
    time
    }}

    clickSubmit: click(
    selector: "button[type='submit'], input[type='submit'], div[role='button']"
    ) {{
    time
    }}

    waitForNavigation(waitUntil: networkIdle) {{
    status
    }}
    }}

    yaml
    Copy code

    ---

    ## 🚫 Output Format Rules
    - Output **only** the BrowserQL code (no markdown, no JSON, no commentary)  
    - Do **not** wrap code in backticks  
    - Do **not** include variables, code fences, or explanations  
    - The query must start with `mutation SubmitForm {{` and end with `}}`
    """

    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    browserql_code = response.choices[0].message.content.strip()

    # Submit the form via Browserless
    submission_resp = requests.post(
        "https://production-sfo.browserless.io/chrome/bql?token=2TFd69pTyWPQ0haaa565b69e977da34a1c6f9eda00cb19316",
        headers={"Content-Type": "application/json"},
        json={"query": browserql_code},
        verify=False
    )
    print("\n--- Browserless Response ---")
    print("Status:", submission_resp.status_code)
    print("Headers:", submission_resp.headers)
    print("Raw Response:", submission_resp.text)
    print("-----------------------------\n")