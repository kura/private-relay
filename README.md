# About
This is the code for my Lambdas that work a private email relay.

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

# Initiating emails using the `NEW_ADDR`
This allows you to email `<NEW_ADDR>_<TOKEN>@<DOMAIN>` with a subject 
matching the following format:
```
<FROM_ADDR> # <TO_ADDR> # <SUBJECT>
```
and have that email forward to the to address, from the from address
with the specified subject.

I.e. a subject line of `some_alias@aliasdomain.tld # webmaster@example.com # Hi`
will send an email as:
```
From: some_alias@aliasdomain.tld
To: webmaster@example.com
Subject: Hi
```

This means you can initiate email conversations from your aliased domain without
needing them to email you first.

# Setup
* DynamoDB table called `emails` with string partition key and index called `message_id`
* DynamoDB table called `history` with string partition key and index called `id`
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
    * `NEW_ADDR`- address to concat with token and domain as `To:`, e.g. `new` (becomes `To: <NEW_ADDR>_<TOKEN>@<DOMAIN>`)
    * `EXPIRY` - how long to keep data in the `emails` table in seconds (Default: 90 days)
    * `EXPIRY_HISTORY` - how long to keep data in the `history` table in seconds (Default: 365 days)

# Optional web Lambda
The web lambda is a simple frontend that allows viewing a history of emails received and the blocklists.
![](https://github.com/kura/private-relay/raw/main/web-preview.png)

## Setup
* Permission to read from the `blocklist` and `history` DynamoDB tables.
* Lambda envvars
    * `AUTH_TOKEN` - The web UI uses HTTP Basic Auth so this is a base64 encoded string of `username:password`, e.g. `echo -n "test:kura | base64`
* Once the Lambda is provisioned, put an API Gateway HTTP API in front of it
    * This just needs to integrate with the Lambda, using version 2.0 with a `GET /` route.