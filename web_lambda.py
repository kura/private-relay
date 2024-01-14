import os

import boto3


AUTH_TOKEN = os.getenv("AUTH_TOKEN")
# In shell: echo -n "username:pass" | base64

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
main {{
  display: block;
}}
h1 {{
  font-size: 2em;
  margin: .67em 0;
}}
.table {{
  width: 80%;
  border-collapse: collapse;
  border-spacing: 0;
  empty-cells: show;
  border: 1px solid #cbcbcb;
}}
.table td, .table th {{
  border-left: 1px solid #cbcbcb;
  border-width: 0 0 0 1px;
  font-size: inherit;
  margin: 0;
  overflow: visible;
  padding: .5em 1em;
}}
.table thead {{
  background-color: #e0e0e0;
  color: #000;
  text-align: left;
  vertical-align: bottom;
}}
.table td {{
  text-align: left;
  vertical-align: top;
}}
.table .address {{
  width: 40%
}}
.table .count {{
  width: 10%;
}}
.table .addresses {{
  width: 50%;
}}
.table tr:nth-child(odd) td, .inner-table tr:nth-child(odd) td {{
  background-color: #ffffff;
}}
.inner-table tr:nth-child(odd) td {{
  background-color: #ffffff !important;
}}
.table tr:nth-child(even) td, .inner-table tr:nth-child(even) td {{
  background-color: #f2f2f2;
}}
.inner-table tr:nth-child(even) td {{
  background-color: #f2f2f2 !important;
}}
.inner-table {{
  width: 100%;
}}
.inner-table .address {{
  width: 80%;
}}
.tabs {{
  position: relative;
  min-height: 200px;
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
<title>Private Relay Statistics</title>
</head>
<body>
<h1>Private Relay Statistics</h1>
<h2>History</h2>
{history}
<h2>Blocklist</h2>
{blocklist}
</body>
<html>
"""

HISTORY_BASE = """
<table class="table">
<thead><tr><th class="address">Address</th>
<th class="count">Emails received</th>
<th class="addresses">From addresses</th></tr></thead>
{rows}
</table>
"""

HISTORY_ROW = """
<tr>
<td class="address mono">{address}</td>
<td class="count mono">{total}</td>
<td class="addresses">
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
<table class="table inner-table">
{rows}
</table>
"""

HISTORY_FROM_ROW = """
<tr><td class="address mono">{address}</td><td class="mono">{total}</td></tr>
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
            rows="".join([HISTORY_FROM_ROW.format(address=addr, total=total) for addr, total in data["from"].items()])
        )
        rows.append(HISTORY_ROW.format(row_id=row_id, address=addr, total=data["total"], from_table=from_table))
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

    body = BASE.format(history=build_history_html(), blocklist=build_blocklist_html())
    return {"statusCode": 200, "body": body, "headers": {"Content-Type": "text/html"}}
