# About
This is the code for my Lambda that works a private email relay.

It's purpose is to allow email sent to my relay domains to be forwarded
to my personal address, and for me to be able to reply from my personal
address without my personal address ever being exposed - a reply sent to
an email will appear as if it is being responded to from the address the
original message was sent to.

# Notes
In general this is written in a way that makes most errors result in a
retry of the Lambda execution. Meaning, email that fails to send will
result in a Lambda retry (the number of retries will depend on the
number of retries configured for the lambda, which by default is 2.)

# Setup
* DynamoDB table called `emails` with string partition key and index called `message_id`
* DynamoDB table called `blocklist` with string partition key and index called `address`
    * Entries in this table should have a format like below
        | address | blocklist |
        | ------- | --------- |
        | `test@test.com` | `from_addr` |
        | `facebook.com` | `from_domain` |
        | `myaddress@mydomain.com` | `to_addr` |
* Lambda envvars
    * `REGION` - AWS Region e.g. `eu-west-1`
    * `S3_BUCKET` - S3 bucket to use, must exist in the defined AWS region, e.g. `my-bucket-name`
    * `DOMAIN` - email domain to service e.g. `test.com`
    * `RECIPIENT` - where to forward the email, e.g. `my.addr@gmail.com`
    * `TOKEN` - some auth token, SHA-1 works well due to length, e.g. `dcc96cbace4351ff561f472de34e72f37fdc115a`
    * `REPLY_ADDR` - address to concat with token and domain as `Reply-To:`, e.g. `replies` (becomes `Reply-To: <REPLY_ADDR>_<TOKEN>@<DOMAIN>`)
    * `NO_REPLY_ADDR` - address to concat with domain, used as `From:` header, e.g. `noreply` (becomes `From: <NO_REPLY_ADDR>@<DOMAIN>`)
    * `BOUNCE_ADDR` - address to concac with domain, used as `From:` header in bounces e.g. `bouncer` (becomes `From: <BOUNCE_ADDR>@<DOMAIN>`)
    * `FROM_ALLOWLIST` - list of addresses allowed to reply, separated by `,`, e.g. `my.addr@gmail.com`
