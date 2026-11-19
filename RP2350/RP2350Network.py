# MicroPython for Raspberry Pi Pico W
import json
import network
import socket
import time

SSID = "Pico Local Chat"
PASSWORD = "Hello123"
MAX_MESSAGES = 30
MAX_NAME_LENGTH = 24
MAX_MESSAGE_LENGTH = 300

ap = network.WLAN(network.AP_IF)
ap.config(essid=SSID, password=PASSWORD)
ap.active(True)

while not ap.active():
    time.sleep_ms(100)

ip = ap.ifconfig()[0]
print("Wi-Fi network:", SSID)
print("Password:", PASSWORD)
print("Open http://" + ip + " on connected devices")

server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", 80))
server.listen(4)

messages = []

page = b"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pico Local Chat</title>
<style>
body{font-family:system-ui,sans-serif;max-width:620px;margin:2rem auto;padding:0 1rem}
#messages{height:55vh;min-height:220px;overflow-y:auto;border:1px solid #bbb;padding:.75rem}
.message{padding:.45rem 0;border-bottom:1px solid #eee;overflow-wrap:anywhere}
form{display:flex;gap:.5rem;margin-top:.75rem}
input{padding:.6rem;min-width:0}#name{width:7rem}#text{flex:1}
button{padding:.6rem 1rem}
</style>
</head>
<body>
<h1>Pico Local Chat</h1>
<p>Messages are shared with devices connected to this Pico and are kept only while it is running.</p>
<div id="messages" aria-live="polite"></div>
<form id="form">
<input id="name" maxlength="24" placeholder="Name" aria-label="Name">
<input id="text" maxlength="300" placeholder="Write a message" aria-label="Message" required>
<button type="submit">Send</button>
</form>
<p id="status">Connecting...</p>
<script>
const list=document.getElementById('messages');
const status=document.getElementById('status');
const form=document.getElementById('form');
let lastSnapshot='';

async function refresh(){
  try{
    const response=await fetch('/api/messages');
    if(!response.ok) throw new Error('Server response');
    const messages=await response.json();
    const snapshot=JSON.stringify(messages);
    if(snapshot!==lastSnapshot){
      list.replaceChildren();
      for(const message of messages){
        const row=document.createElement('div');
        row.className='message';
        const label=document.createElement('strong');
        label.textContent=message.name+': ';
        row.append(label,document.createTextNode(message.text));
        list.append(row);
      }
      list.scrollTop=list.scrollHeight;
      lastSnapshot=snapshot;
    }
    status.textContent='Connected';
  }catch(error){
    status.textContent='Chat connection lost; retrying...';
  }
}

form.addEventListener('submit',async event=>{
  event.preventDefault();
  const name=document.getElementById('name').value.trim()||'Guest';
  const input=document.getElementById('text');
  const text=input.value.trim();
  if(!text) return;
  try{
    const response=await fetch('/api/send',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,text})
    });
    if(!response.ok) throw new Error('Message not sent');
    input.value='';
    await refresh();
  }catch(error){
    status.textContent='Could not send message; please try again.';
  }
});

refresh();
setInterval(refresh,1000);
</script>
</body>
</html>
"""


def read_request(client):
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 2048:
        chunk = client.recv(512)
        if not chunk:
            return None
        data += chunk

    separator = data.find(b"\r\n\r\n")
    if separator < 0:
        return None

    header_data = data[:separator]
    body = data[separator + 4:]
    lines = header_data.split(b"\r\n")
    request_parts = lines[0].split()
    if len(request_parts) < 2:
        return None

    content_length = 0
    for header in lines[1:]:
        if header.lower().startswith(b"content-length:"):
            try:
                content_length = int(header.split(b":", 1)[1].strip())
            except ValueError:
                return None
            break

    if content_length < 0 or content_length > 1024:
        return None

    while len(body) < content_length:
        chunk = client.recv(min(512, content_length - len(body)))
        if not chunk:
            return None
        body += chunk

    path = request_parts[1].split(b"?", 1)[0]
    return request_parts[0], path, body[:content_length]


def send_response(client, status, content_type, body, location=None):
    response = (
        b"HTTP/1.1 " + status + b"\r\n"
        b"Content-Type: " + content_type + b"\r\n"
        b"Connection: close\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n"
    )
    if location is not None:
        response = response.replace(
            b"Connection: close\r\n",
            b"Connection: close\r\nLocation: " + location + b"\r\n",
        )
    response += body
    client.sendall(response)


while True:
    client, address = server.accept()
    try:
        request = read_request(client)
        if request is None:
            send_response(client, b"400 Bad Request", b"text/plain", b"Invalid request")
            continue

        method, path, body = request
        if method == b"GET" and path == b"/":
            send_response(client, b"200 OK", b"text/html; charset=utf-8", page)
        elif method == b"GET" and path == b"/api/messages":
            response_body = json.dumps(messages).encode()
            send_response(
                client,
                b"200 OK",
                b"application/json; charset=utf-8",
                response_body,
            )
        elif method == b"POST" and path == b"/api/send":
            try:
                message = json.loads(body)
            except ValueError:
                send_response(
                    client,
                    b"400 Bad Request",
                    b"text/plain",
                    b"Invalid message",
                )
                continue

            if not isinstance(message, dict):
                send_response(
                    client,
                    b"400 Bad Request",
                    b"text/plain",
                    b"Invalid message",
                )
                continue

            name = message.get("name")
            text = message.get("text")
            if not isinstance(name, str) or not isinstance(text, str):
                send_response(
                    client,
                    b"400 Bad Request",
                    b"text/plain",
                    b"Name and message must be text",
                )
                continue

            name = name.strip()[:MAX_NAME_LENGTH] or "Guest"
            text = text.strip()[:MAX_MESSAGE_LENGTH]
            if not text:
                send_response(
                    client,
                    b"400 Bad Request",
                    b"text/plain",
                    b"Message cannot be empty",
                )
                continue

            messages.append({"name": name, "text": text})
            if len(messages) > MAX_MESSAGES:
                del messages[0]
            send_response(client, b"201 Created", b"text/plain", b"Sent")
        else:
            send_response(
                client,
                b"302 Found",
                b"text/plain",
                b"",
                b"http://" + ip.encode() + b"/",
            )
    finally:
        client.close()
