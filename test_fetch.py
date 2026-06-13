import requests
import sys

s = requests.Session()
login_url = "https://dev.vingren.me/casehub/login"
r_get = s.get(login_url)
# Typically we just POST to login
r_post = s.post(login_url, data={"email": "victor@vingren.me", "password": "dev123"}, allow_redirects=False)
if r_post.status_code not in [302, 303]:
    print("Login failed with status:", r_post.status_code)
    sys.exit(1)

emails_url = "https://dev.vingren.me/casehub/emails"
r_emails = s.get(emails_url)
print("STATUS CODE:", r_emails.status_code)
if r_emails.status_code != 200:
    print("RESPONSE:", r_emails.text[:500])
else:
    print("It returned 200. Let's see the title:", r_emails.text.split("</title>")[0].split("<title>")[-1] if "<title>" in r_emails.text else "No title")
