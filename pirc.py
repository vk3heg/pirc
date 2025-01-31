import selectors
import socket
from sys import argv

class TcpServer:
    def __init__(self, host="localhost", port=1234, max_message_size=1000, max_pending_clients=5) -> None:
        self.host = host
        self.port = port
        self.max_pending_clients = max_pending_clients
        self.max_message_size = max_message_size

    def run(self) -> None:
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.setblocking(False)
        self.listener.bind((self.host, self.port))
        self.listener.listen(self.max_pending_clients)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.listener, selectors.EVENT_READ)
        while True:
            events = self.selector.select()
            for key, _mask in events:
                if key.fileobj == self.listener: self.accept()
                else: self.read(key.fileobj, key.data)

    def accept(self) -> None:
        client, _address = self.listener.accept()
        client_data = self.create_client_data(client)
        client.setblocking(False)
        self.selector.register(client, selectors.EVENT_READ, client_data)
            
    def read(self, client: socket.socket, client_data) -> None:
        try:
            message = client.recv(self.max_message_size)
            if not message: raise
            self.handle(client_data, message)
        except:
            # Treat all errors as disconnections
            self.selector.unregister(client)
            client.close()

    def send(self, client: socket.socket, message: bytes):
        client.sendall(message)

    def broadcast(self, message: bytes):
        for _f, k in self.selector.get_map().items():
            if not k.fileobj == self.listener:
                self.send(k.fileobj, message)

    def create_client_data(self, client: socket.socket):
        raise NotImplementedError()

    def handle(self, client_data, message: bytes) -> None:
        raise NotImplementedError()

class ChatServer(TcpServer):
    def create_client_data(self, client):
        return None
    
    def handle(self, client_data, message: bytes) -> None:
        self.broadcast(message)

server = ChatServer()
server.run()
