import email
import email.policy
import email.utils
import email.message
import email.mime.multipart
import email.mime.text
import email.parser
import os
import time
import traceback
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError


# us-east-1
REGION = os.getenv("REGION")

# your-bucket-name
S3_BUCKET = os.getenv("S3_BUCKET")

# domain.tld
DOMAIN = os.getenv("DOMAIN")

# any token, a SHA1 token works well because of only 32 character length
TOKEN = os.getenv("TOKEN")

# user@domain.tld
RECIPIENT = os.getenv("RECIPIENT")

# replies  -- this will become <REPLY_ADDR>_<TOKEN>@<DOMAIN>
REPLY_ADDR = os.getenv("REPLY_ADDR")

# noreply  -- this will become <NO_REPLY_ADDR>@<DOMAIN>
NO_REPLY_ADDR = os.getenv("NO_REPLY_ADDR")

#  bouncer  -- this will become <BOUNCE_ADDR>@<DOMAIN>
BOUNCE_ADDR = os.getenv("BOUNCE_ADDR")

# user1@domain.tld,user2@domain.tld
FROM_ALLOWLIST = os.getenv("FROM_ALLOWLIST")
FROM_ALLOWLIST = FROM_ALLOWLIST.replace(" ", "").split(",") if FROM_ALLOWLIST else None

EXPIRY = int(os.getenv("EXPIRY") or 7776000)  # Default: 90 days
HISTORY_EXPIRY = int(os.getenv("HISTORY_EXPIRY") or 31536000)  # Default: 365 days


class CreateError(Exception):
    pass


class Bounce(Exception):
    message_id = None
    recipient = None
    reason = None

    def __init__(self, message_id, recipient, reason):
        self.message_id = message_id
        self.recipient = recipient
        self.reason = reason
        super().__init__()


def put_db_message(message_id, to_addr, from_addr):
    print(f"Write Message-ID: '{message_id}' to DB")
    boto3.resource("dynamodb").Table("emails").put_item(
        Item={
            "message_id": message_id,
            "to": email.utils.parseaddr(to_addr)[1].lower(),
            "from": email.utils.parseaddr(from_addr)[1].lower(),
            "expires": int(time.time()) + EXPIRY
        }
    )


def get_db_message(message_id):
    print(f"Read Message-ID: '{message_id}' from DB")
    return boto3.resource("dynamodb").Table("emails").get_item(Key={"message_id": message_id})["Item"]


def put_db_history(to_addr, from_addr):
    uuid = str(uuid4())
    to_addr = email.utils.parseaddr(to_addr)[1]
    from_addr = email.utils.parseaddr(from_addr)[1]
    if f"@{DOMAIN}" in to_addr:
        print(f"Write history to DB")
        boto3.resource("dynamodb").Table("history").put_item(
            Item={
                "id": uuid,
                "to": to_addr.lower(),
                "from": from_addr.lower(),
                "expires": int(time.time()) + HISTORY_EXPIRY,
            }
        )


def get_message_from_s3(message_id):
    print(f"Read Message-ID: '{message_id}' from S3")
    return boto3.client("s3").get_object(Bucket=S3_BUCKET, Key=message_id)["Body"].read()


def get_db_blocklist(address):
    try:
        return boto3.resource("dynamodb").Table("blocklist").get_item(Key={"address": address})["Item"]
    except KeyError:
        return None


def bounce_blocklist(message_id, to_addr, from_addr):
    if get_db_blocklist(to_addr):
        print(f"'{to_addr}' is in BLOCKLIST: 'to_addr'")
        raise Bounce(message_id=message_id, recipient=to_addr, reason="DoesNotExist")

    if get_db_blocklist(from_addr):
        print(f"'{from_addr}' is in BLOCKLIST: 'from_addr'")
        raise Bounce(message_id=message_id, recipient=to_addr, reason="ContentRejected")

    if get_db_blocklist(from_addr.partition("@")[2]):
        print(f"""'{from_addr.partition("@")[2]}' is in BLOCKLIST: 'from_domain'""")
        raise Bounce(message_id=message_id, recipient=to_addr, reason="ContentRejected")


def sender_auth(to_addr, from_addr):
    if to_addr.partition("@")[0].partition("_")[2] != TOKEN:
        raise CreateError("Invalid token")

    if from_addr not in FROM_ALLOWLIST:
        raise CreateError(f"'{from_addr}' not in allow list ('{FROM_ALLOWLIST}')")


def send_email(message):
    return boto3.client("sesv2", REGION).send_email(**message)


def send_bounce(message_id, recipient, reason):
    try:
        resp = boto3.client("ses", REGION).send_bounce(
            OriginalMessageId=message_id,
            BounceSender=f"{BOUNCE_ADDR}@{DOMAIN}",
            BouncedRecipientInfoList=[{"Recipient": recipient, "BounceType": reason}],
        )
    except ClientError as e:
        print(f"""Failed to send email: {e.response["Error"]["Message"]}""")
        raise e
    else:
        print(f"""Bounce sent! Message-ID: '{resp["MessageId"]}'""")


def create_message(message_id):
    obj = email.message_from_string(get_message_from_s3(message_id).decode(), policy=email.policy.default)

    msg = email.mime.multipart.MIMEMultipart()
    body = obj.get_body()
    msg.attach(body)

    to_addr = email.utils.parseaddr(obj.get("To"))[1]
    from_addr = email.utils.parseaddr(obj.get("From"))[1]
    in_reply_to = obj.get("In-Reply-To")
    subject = obj.get("Subject")

    bounce_blocklist(message_id, to_addr, from_addr)

    for payload in obj.get_payload():
        if isinstance(payload, email.message.EmailMessage) and payload.is_attachment():
            msg.attach(payload)

    if to_addr == f"{REPLY_ADDR}_{TOKEN}@{DOMAIN}" and in_reply_to:
        sender_auth(to_addr, from_addr)
        clean_in_reply_to = in_reply_to.replace("<", "").replace(">", "").partition("@")[0]
        r = get_db_message(clean_in_reply_to)
        sender = r["to"]
        recipient = r["from"]
    else:
        sender = f""""{from_addr}" [Relayed from "{to_addr}"] """ f"""<{NO_REPLY_ADDR}@{DOMAIN}>"""
        recipient = RECIPIENT
        msg["Reply-To"] = f"{REPLY_ADDR}_{TOKEN}@{DOMAIN}"

    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if obj.get_all("References"):
        msg["References"] = "\r\n ".join(obj.get_all("References"))

    return (
        to_addr,
        from_addr,
        {
            "FromEmailAddress": sender,
            "Destination": {"ToAddresses": [recipient]},
            "ReplyToAddresses": [msg["Reply-To"]] if "Reply-To" in msg else [],
            "Content": {"Raw": {"Data": msg.as_string().encode()}},
        },
    )


def lambda_handler(event, context):
    message_id = event["Records"][0]["ses"]["mail"]["messageId"]
    print(f"Received Message-ID: '{message_id}'")

    try:
        to_addr, from_addr, message = create_message(message_id)
    except Bounce as b:
        send_bounce(b.message_id, b.recipient, b.reason)
        return True
    except CreateError as e:
        print(traceback.format_exc())
        return True
    except Exception as e:
        raise e

    try:
        resp = send_email(message)
    except ClientError as e:
        print(f"""Failed to send email: {e.response["Error"]["Message"]}""")
        raise e
    else:
        print(f"""Email sent! Message-ID: '{resp["MessageId"]}'""")

    if to_addr != f"{REPLY_ADDR}_{TOKEN}@{DOMAIN}":
        try:
            put_db_message(resp["MessageId"], to_addr, from_addr)
            put_db_history(to_addr, from_addr)
        except Exception as e:
            print(traceback.format_exc())
            pass
