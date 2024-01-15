import os
from base64 import b64decode
from urllib.parse import parse_qs

import boto3
from botocore.exceptions import ClientError


# In shell: echo -n "username:pass" | base64
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

# us-east-1
REGION = os.getenv("REGION")

# domain.tld
DOMAIN = os.getenv("DOMAIN")

UNATHED_RESP = {
    "statusCode": 401,
    "statusDescription": "Unauthorized",
    "headers": {
        "WWW-Authenticate": "Basic realm=\"Private Relay\", charset=\"UTF-8\""
    }
}

BASE = """
<!doctype html>
<html>
<head>
<style type="text/css">
html {{
  line-height:1.15;
}}
body {{
  margin: 1em;
}}
h1 {{
  font-size: 2em;
  margin: .67em 0;
}}
.form input[type="text"],
.form input[type="email"],
.form textarea {{
    padding: 0.5em 0.6em;
    display: inline-block;
    border: 1px solid #ccc;
    box-shadow: inset 0 1px 3px #ddd;
    border-radius: 4px;
    vertical-align: middle;
    box-sizing: border-box;
    width: 600px;
}}
.form input[type="text"]:focus,
.form input[type="email"]:focus,
.form textarea:focus {{
    outline: 0;
    border-color: #129FEA;
}}
.form label {{
    margin: 0.5em 0 0.2em;
}}
.form fieldset {{
    margin: 0;
    padding: 0.35em 0 0.75em;
    border: 0;
}}
.form legend {{
    display: block;
    width: 100%;
    padding: 0.3em 0;
    margin-bottom: 0.3em;
    color: #333;
    border-bottom: 1px solid #e5e5e5;
}}
.form-stacked input[type="text"],
.form-stacked input[type="email"],
.form-stacked label,
.form-stacked textarea {{
    display: block;
    margin: 0.25em 0;
}}
.button {{
    font-family: inherit;
    font-size: 100%;
    padding: 0.5em 1em;
    color: rgba(0, 0, 0, 0.80);
    border: none rgba(0, 0, 0, 0);
    background-color: #E6E6E6;
    text-decoration: none;
    border-radius: 2px;
}}
.button-hover,
.button:hover,
.button:focus {{
    background-image: linear-gradient(transparent, rgba(0,0,0, 0.05) 40%, rgba(0,0,0, 0.10));
}}
.button:focus {{
    outline: 0;
}}
.button-active,
.button:active {{
    box-shadow: 0 0 0 1px rgba(0,0,0, 0.15) inset, 0 0 6px rgba(0,0,0, 0.20) inset;
    border-color: #000;
}}
</style>
<title>Private Relay - Create</title>
</head>
<body>
<h1>Private Relay - Create</h1>
{content}
</body>
<html>
"""

FORM_CONTENT = """
<form action="/send" method="POST" class="form form-stacked">
<fieldset>
  <legend>Send email</legend>
  <label for="from">From  (@{domain} will automatically be appended)</label>
  <input type="email" id="from" name="from" placeholder="someone@{domain}" />
  <label for="to">To</label>
  <input type="email" id="to" name="to" placeholder="user@domain.tld" />
  <label for="subject">Subject</label>
  <input type="text" id="subject" name="subject" placeholder="Hi, how are you?" />
  <label for="body">Body</label>
  <textarea id="body" name="body" rows="40" cols="40"></textarea>
  <button type="submit" class="button">Send</button>
</fieldset>
</form>
"""

SEND_CONTENT = """
<div>{message}</div>
<div><a href="/">Back to create page</a></div>
"""


def send_email(to_addr, from_addr, subject, body):
    from_addr = f"{from_addr}@{DOMAIN}"

    return boto3.client("sesv2", REGION).send_email(
        FromEmailAddress=from_addr,
        Destination={"ToAddresses": [to_addr,]},
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "utf-8"},
                "Body": {"Text": {"Data": body, "Charset": "utf-8"}},
            }
        }
    )


class AuthError(Exception):
    pass


def do_auth(event):
    try:
        if event["headers"]["authorization"].split(" ")[1] == AUTH_TOKEN:
            return True
        else:
            raise AuthError()
    except:
        raise AuthError()


def lambda_handler(event, context):
    try:
        do_auth(event)
    except AuthError:
        return UNATHED_RESP

    if event["routeKey"] == "POST /send":
        resp_content = "Message sent"
        data = {k.decode(): v for k, v in parse_qs(b64decode(event["body"])).items()}
        from_addr = data.get("from")[0].decode()
        to_addr = data.get("to")[0].decode()
        subject = "".join([x.decode() for x in data.get("subject")])
        body = "".join([x.decode() for x in data.get("body")])
        try:
            resp = send_email(to_addr, from_addr, subject, body)
            resp_content = f"""Message with Message-ID '{resp["MessageId"]} sent!'"""
        except ClientError as e:
            resp_content = e.response["Error"]["Message"]
        body = BASE.format(content=SEND_CONTENT.format(message=resp_content))
    else:
        body = BASE.format(content=FORM_CONTENT.format(domain=DOMAIN))
    
    return {"statusCode": 200, "body": body, "headers": {"Content-Type": "text/html"}}
