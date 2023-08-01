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

import boto3
from botocore.exceptions import ClientError


REGION = os.getenv("REGION")
S3_BUCKET = os.getenv("S3_BUCKET")
RECIPIENT = os.getenv("RECIPIENT")
REPLY_ADDR = os.getenv("REPLY_ADDR")  # replies@domain.tld
NO_REPLY_ADDR = os.getenv("NO_REPLY_ADDR")  # noreply@domain.tld
FROM_ALLOWLIST = os.getenv("FROM_ALLOWLIST")  # user1@domain.tld,user2@domain.tld
FROM_DOMAIN_BLOCKLIST = os.getenv("FROM_DOMAIN_BLOCKLIST") or None  # domain1.tld,domain2.tld
FROM_ADDR_BLOCKLIST = os.getenv("FROM_ADDR_BLOCKLIST") or None  # user1@domain1.tld,user1@domain2.tld
TO_ADDR_BLOCKLIST = os.getenv("TO_ADDR_BLOCKLIST") or None  # user1@domain1.tld,user1@domain2.tld
BOUNCE_ADDR = os.getenv("BOUNCE_ADDR")  #  bouncer@domain.tld


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


def write_item_to_db(message_id, to_addr, from_addr):
    print(f"Write Message-ID: '{message_id}' to DB")
    db = boto3.resource("dynamodb").Table("emails")
    db.put_item(
        Item={
            "message_id": message_id,
            "to": email.utils.parseaddr(to_addr)[1],
            "from": email.utils.parseaddr(from_addr)[1],
            "expires": int(time.time()) + 7776000,  # 90 days
        }
    )


def get_item_from_db(message_id):
    print(f"Read Message-ID: '{message_id}' from DB")
    db = boto3.resource("dynamodb").Table("emails")
    return db.get_item(Key={"message_id": message_id})["Item"]


def get_message_from_s3(message_id):
    print(f"Read Message-ID: '{message_id}' from S3")
    object_s3 = boto3.client("s3").get_object(Bucket=S3_BUCKET, Key=message_id)
    return object_s3["Body"].read()


def bounce_blocklist(message_id, to_addr, from_addr):
    if (
        TO_ADDR_BLOCKLIST and
        to_addr in TO_ADDR_BLOCKLIST.replace(" ", "").split(",")
    ):
        print(f"'{to_addr}' is in TO_ADDR_BLOCKLIST: '{TO_ADDR_BLOCKLIST}'")
        raise Bounce(message_id=message_id, recipient=to_addr, reason="DoesNotExist")

    if (
        FROM_DOMAIN_BLOCKLIST and
        from_addr.partition("@")[2] in FROM_DOMAIN_BLOCKLIST.replace(" ", "").split(",")
    ):
        print(
            f"'{from_addr}' is in FROM_DOMAIN_BLOCKLIST: '{FROM_DOMAIN_BLOCKLIST}'"
        )
        raise Bounce(message_id=message_id, recipient=to_addr, reason="ContentRejected")

    if (
        FROM_ADDR_BLOCKLIST and
        from_addr in FROM_ADDR_BLOCKLIST.replace(" ", "").split(",")
    ):
        print(
            f"'{from_addr}' is in FROM_ADDR_BLOCKLIST: '{FROM_ADDR_BLOCKLIST}'"
        )
        raise Bounce(message_id=message_id, recipient=to_addr, reason="ContentRejected")


def create_message(message_id):
    obj = email.message_from_string(
        get_message_from_s3(message_id).decode(), policy=email.policy.default
    )

    msg = email.mime.multipart.MIMEMultipart()
    body = obj.get_body()
    msg.attach(body)

    to_addr = email.utils.parseaddr(obj.get("To"))[1]
    from_addr = email.utils.parseaddr(obj.get("From"))[1]
    in_reply_to = obj.get("In-Reply-To")

    bounce_blocklist(message_id, to_addr, from_addr)

    for payload in obj.get_payload():
        if (
            isinstance(payload, email.message.EmailMessage)
            and payload.is_attachment()
        ):
            msg.attach(payload)

    if to_addr == REPLY_ADDR and in_reply_to:
        clean_in_reply_to = (
            in_reply_to.replace("<", "").replace(">", "").partition("@")[0]
        )
        print(f"Message is a reply to Message-ID: '{clean_in_reply_to}'")
        if from_addr not in FROM_ALLOWLIST.replace(" ", "").split(","):
            raise CreateError(
                f"'{from_addr}' not in allow list ('{FROM_ALLOWLIST}')"
            )
        r = get_item_from_db(clean_in_reply_to)
        sender = r["to"]
        recipient = r["from"]
    else:
        sender = (
            f""""{from_addr}" [Relayed from "{to_addr}"] <{NO_REPLY_ADDR}>"""
        )
        recipient = RECIPIENT
        msg["Reply-To"] = REPLY_ADDR

    msg["Subject"] = obj.get("Subject")
    msg["From"] = sender
    msg["To"] = recipient

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if obj.get_all("References"):
        msg["References"] = "\r\n ".join(obj.get_all("References"))

    return (
        to_addr, from_addr,
        {
            "FromEmailAddress": sender,
            "Destination": {"ToAddresses": [recipient]},
            "ReplyToAddresses": [msg["Reply-To"]] if "Reply-To" in msg else [],
            "Content": {"Raw": {"Data": msg.as_string().encode()}},
        },
    )


def send_email(message):
    client_ses = boto3.client("sesv2", REGION)
    return client_ses.send_email(**message)


def send_bounce(message_id, recipient, reason):
    try:
        client_ses = boto3.client("ses", REGION)
        resp = client_ses.send_bounce(
            OriginalMessageId=message_id,
            BounceSender=BOUNCE_ADDR,
            BouncedRecipientInfoList=[
                {
                    "Recipient": recipient,
                    "BounceType": reason
                }
            ],
        )
    except ClientError as e:
        print(f"""Failed to send email: {e.response["Error"]["Message"]}""")
        raise e
    else:
        print(f"""Bounce sent! Message-ID: '{resp["MessageId"]}'""")


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

    if to_addr != REPLY_ADDR:
        try:
            write_item_to_db(resp["MessageId"], to_addr, from_addr)
        except Exception as e:
            print(traceback.format_exc())
            pass
