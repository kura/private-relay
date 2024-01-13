import os

import boto3
from botocore.exceptions import ClientError


PW = os.getenv("PW")

BASE = """
<!DOCTYPE html>
<style>
td, th {{
  text-align: left;
  vertical-align: top;
}}
table {{
  width: 80%;
}}
.tabs {{
  position: relative;
  min-height: 200px; /* This part sucks */
  clear: both;
  margin: 25px 0;
}}
.tab {{
  float: left;
}}
.tab label {{
  background: #eee;
  padding: 10px;
  border: 1px solid #ccc;
  margin-left: -1px;
  position: relative;
  left: 1px;
}}
.tab [type="radio"] {{
  opacity: 0;
}}
.content {{
  position: absolute;
  top: 28px;
  left: 0;
  background: white;
  right: 0;
  bottom: 0;
  padding: 20px;
  border: 1px solid #ccc;
  overflow: hidden;
}}
.content > * {{
  opacity: 0;
  transform: translateX(-100%);
  transition: all 0.01s ease;
}}
[type="radio"]:focus ~ label {{
  ouline: 2px solid blue;
}}
[type="radio"]:checked ~ label {{
  background: white;
  border-bottom: 1px solid white;
  z-index: 2;
}}
[type="radio"]:checked ~ label ~ .content {{
  z-index: 1;
}}
[type="radio"]:checked ~ label ~ .content > * {{
  opacity: 1;
  transform: translateX(0);
}}
.detail,
.show,
.hide:target {{
  display: none;
}}
.hide:target + .show,
.hide:target ~ .detail {{
  display: block;
}}
.mono, li {{
  font-family: monospace;
  font-size: 1rem;
}}
</style>
<title>Stats</title>
<h1>Stats</h1>
<h2>History</h2>
{history}
<h2>Blocklist</h2>
{blocklist}
"""

HISTORY_BASE = """
<table>
<tr><th>Address</th><th>Emails received</th><th>From addresses</th></tr>
{rows}
</table>
"""

HISTORY_ROW = """
<tr>
<td class="mono">{address}</td>
<td class="mono">{total}</td>
<td>
<!--
<a id="hide{row_id}" href="#hide{row_id}" class="hide">+ Show</a>
<a id="show{row_id}" href="#show{row_id}" class="show">- Hide</a>
<div class="detail">{from_table}</div>
-->
{from_table}
</td>
</tr>
"""

HISTORY_FROM_TABLE = """
<table>
{rows}
</table>
"""

HISTORY_FROM_ROW = """
<tr><td class="mono">{address}</td><td class="mono">{total}</td></tr>
"""

BLOCKLIST_BASE = """
<div class="tabs">
  <div class="tab">
    <input type="radio" id="tab-1" name="tab-group-1" checked>
    <label for="tab-1">TO</label>
    <div class="content">
      <p><ul>{to_list}</ul></p>
    </div>
  </div>
  <div class="tab">
    <input type="radio" id="tab-2" name="tab-group-1">
    <label for="tab-2">FROM</label>
    <div class="content">
      <p><ul>{from_list}</ul></p>
    </div>
  </div>
  <div class="tab">
    <input type="radio" id="tab-3" name="tab-group-1">
    <label for="tab-3">DOMAIN</label>
    <div class="content">
      <p><ul>{domain_list}</ul></p>
    </div>
  </div>
</div>
"""


def get_db_history():
    return boto3.resource("dynamodb").Table("history").scan()["Items"]


def build_history_table():
    table = {}
    for item in get_db_history():
        to_addr = item["to"]
        from_addr = item["from"]
        if not to_addr in table:
            table[to_addr] = {"from": {from_addr: 1}, "total": 1}
        else:
            table[to_addr]["total"] += 1
            if not from_addr in table[to_addr]["from"]:
                table[to_addr]["from"][from_addr] = 1
            else:
                table[to_addr]["from"][from_addr] += 1
    return table


def build_history_html():
    table = build_history_table()
    rows = []
    row_id = 1
    for addr, data in table.items():
        from_table = HISTORY_FROM_TABLE.format(
            rows="".join([
                HISTORY_FROM_ROW.format(address=addr, total=total)
                for addr, total in data["from"].items()
            ])
        )
        rows.append(HISTORY_ROW.format(
            row_id=row_id, address=addr, total=data["total"], from_table=from_table
        ))
        row_id += 1
    return HISTORY_BASE.format(rows="".join(rows))


def get_db_blocklist():
    return boto3.resource("dynamodb").Table("blocklist").scan()["Items"]


def build_blocklist_table():
    table = {"to_addr": [], "from_addr": [], "domain": []}
    for item in get_db_blocklist():
        table[item["blocklist"]].append(item["address"])
    return table


def build_blocklist_html():
    table = build_blocklist_table()
    return BLOCKLIST_BASE.format(
        to_list="".join([f"<li>{addr}</li>" for addr in table["to_addr"]]),
        from_list="".join([f"<li>{addr}</li>" for addr in table["from_addr"]]),
        domain_list="".join([f"<li>{addr}</li>" for addr in table["domain"]]),
    )


def lambda_handler(event, context):
    no = {
        "statusCode": 401,
        "body": "<strong>Go away</strong>",
        "headers": {"Content-Type": "text/html"}
    }
    try:
        if event["queryStringParameters"]["pw"] != PW:
            return no
    except KeyError:
        return no

    body = BASE.format(history=build_history_html(), blocklist=build_blocklist_html())
    return {"statusCode": 200, "body": body, "headers": {"Content-Type": "text/html"}}