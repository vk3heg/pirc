import selectors
import socket
from sys import argv

# Arguments: HOST PORT
host, port = argv[-2], int(argv[-1])
max_message_size = 1000
max_pending_clients = 5

# Bind top-level listener for registering new client connections
listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Unnecessary
listener.bind((host, port))
listener.listen(max_pending_clients)
listener.setblocking(False)

selector = selectors.DefaultSelector()

# Main message handler
def process(data: bytes) -> None:
    # Send to all sockets, except the top-level listener
    print(f"Received: {repr(data)}")
    for _f, k in selector.get_map().items():
        client: socket.socket = k.fileobj
        if not client == listener:
            client.sendall(data)

# Helpers
def client_add(listener: socket.socket) -> None:
    client, _address = listener.accept()
    client.setblocking(False)
    selector.register(client, selectors.EVENT_READ)
    print("Client connected!")

def client_handle(client: socket.socket) -> None:
    client = key.fileobj
    try:
        data = client.recv(max_message_size)
        if not data:
            # No input implies disconnected
            raise
        process(data)
    except:
        # Treat all errors as disconnections
        print("Client disconnected!")
        selector.unregister(client)
        client.close()

# Add top-level listener to list for `select`
selector.register(listener, selectors.EVENT_READ)
print(f"Listening on {host}:{port}...")

# Process events indefinitely
while True:
    events = selector.select()
    for key, _mask in events:
        if key.fileobj == listener:
            # Top-level listener has a new client to add
            client_add(listener)
        else:
            # Client has data ready for reading
            client_handle(key.fileobj)
