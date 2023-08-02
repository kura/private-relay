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