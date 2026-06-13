import requests
import sys

s = requests.Session()
login_url = "https://dev.vingren.me/casehub/login"
r_post = s.post(login_url, data={"email": "victor@vingren.me", "password": "dev123"}, allow_redirects=False)

emails_url = "https://dev.vingren.me/casehub/emails"
r_list = s.get(emails_url)
import re
match = re.search(r'data-id="(\d+)"', r_list.text)
if not match:
    print("No emails found to view.")
    sys.exit(0)

email_id = match.group(1)
view_url = f"https://dev.vingren.me/casehub/emails/{email_id}"
print(f"Fetching {view_url} ...")
r_view = s.get(view_url)
print("STATUS CODE:", r_view.status_code)
if r_view.status_code != 200:
    print("RESPONSE:", r_view.text[:1000])
else:
    print("It returned 200.")
