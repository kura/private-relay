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
        "WWW-Authenticate": "Basic"
    }
}

BASE = """
<!doctype html>
<html>
<head>
<style>
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
input[type=email], input[type=text], textarea {{
  padding: .5em .6em;
  display: inline-block;
  border: 1px solid #ccc;
  box-shadow: inset 0 1px 3px #ddd;
  border-radius:4px;
  vertical-align:middle;
  box-sizing:border-box
}}
input:not([type]) {{
  padding:.5em .6em;
  display:inline-block;
  border:1px solid #ccc;
  box-shadow:inset 0 1px 3px #ddd;
  border-radius:4px;
  box-sizing:border-box;
}}
input[type=email]:focus, input[type=text]:focus, textarea:focus {{
  outline:0;
  border-color:#129fea;
}}
input:not([type]):focus {{
  outline:0;
  border-color:#129fea;
}}
</style>
<title>Send Email</title>
</head>
<body>
<h1>Send Email</h1>
{content}
</body>
<html>
"""

FORM_CONTENT = """
<form action="/send" method="POST">
<fieldset>
  <legend>Send email</legend>
  <div>
  <label for="from">From: </label>
  <input id="from" name="from" type="text" />@{domain}
  </div>
  <div>
  <label for="to">To:</label>
  <input id="to" name="to" type="text" />
  </div>
  <div>
  <label for="subject">Subject:</label>
  <input id="subject" name="subject" type="text" />
  </div>
  <div>
  <label for="body">Body:</label>
  <textarea id="body" name="body" rows="40" cols="40"></textarea>
  </div>
  <div>
  <button type="submit">Send</button>
  </div>
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
