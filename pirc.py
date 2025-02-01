import re
import selectors
import socket
from enum import Enum
from sys import argv

# Generic select-based TCP server
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

    def broadcast(self, message: bytes, excluded: socket.socket|None = None):
        for _f, k in self.selector.get_map().items():
            if not (k.fileobj == self.listener or k.fileobj == excluded):
                self.send(k.fileobj, message)

    def create_client_data(self, client: socket.socket):
        raise NotImplementedError()

    def handle(self, client_data, message: bytes) -> None:
        raise NotImplementedError()

# IRC command parser
command_pattern = r"^(?P<source>:[a-zA-Z0-9@#*_.+!\-]+ )?(?P<command>[A-Z]+)(?P<subcommands>( [a-zA-Z0-9@#*_.+!\-]+)*)( :(?P<content>.*))?$"

class Command:
    def __init__(self, text: str) -> None:
        # Parse message
        print(f"In: {text}")
        match = re.match(command_pattern, text)
        if not match: raise SyntaxError("Invalid message received!")
        source = match["source"]
        subcommands = match["subcommands"]
        self.source = source[1:-1] if source else None
        self.command = match["command"]
        self.subcommands = subcommands.strip().split(" ") if subcommands else None
        self.content = match["content"]
    
    def __repr__(self):
        return f"Command: {self.command}, Subcommands: {repr(self.subcommands)}, Content: {self.content}"

class ClientRegistration:
    def __init__(self, client: socket.socket) -> None:
        self.client = client
        self.nick = "?"
        self.user = "?"
        self.host = "internet"

    def id(self) -> str:
        return f"{self.nick}!{self.user}@{self.host}"

# Server
class IrcServer(TcpServer):
    def __init__(self, host="localhost", port=1234, max_pending_clients=5, network_name="pircnet", server_name="pirc"):
        super().__init__(host, port, 512, max_pending_clients)
        self.network_name = network_name
        self.server_name = server_name
        self.version = 0.1

    def send(self, client: socket.socket, message: str):
        print(f"Out: {message}")
        return super().send(client, f"{message}\r\n".encode("ascii"))
    
    def broadcast_others(self, client_data: ClientRegistration, message: str):
        self.broadcast(message, client_data.client)

    def create_client_data(self, client: socket.socket) -> ClientRegistration:
        return ClientRegistration(client)
    
    def handle(self, client_data: ClientRegistration, message: bytes) -> None:
        # TODO: Support non-ASCII
        text = message.decode("ascii")
        lines = text.strip().split("\r\n")
        for line in lines:
            self.handle_command(client_data, Command(line))
    
    def reply(self, client_data: ClientRegistration, text: str) -> None:
        self.send(client_data.client, text)

    def reply_numeric(self, client_data: ClientRegistration, number: int, text: str) -> None:
        self.reply(client_data, f"{str(number).zfill(3)} {client_data.nick} {text}")

    def handle_command(self, client_data: ClientRegistration, command: Command) -> None:
        print(f"Received: {repr(command)}")
        match command.command:
            case "CAP":
                match command.subcommands[0]:
                    case "LS":
                        self.reply(client_data, "CAP * ACK")
            case "NICK":
                # TODO: Check for duplicates?
                client_data.nick = command.subcommands[0]
            case "USER":
                client_data.user = command.subcommands[0]
                self.reply_numeric(client_data, 1, f":Welcome, {client_data.id()}")
                self.reply_numeric(client_data, 2, f":Your host is {self.server_name}, running version {self.version}")
                self.reply_numeric(client_data, 3, ":This server was created today")
                self.reply_numeric(client_data, 4, f"{self.server_name} {self.version}  ")
                self.reply_numeric(client_data, 5, f"NETWORK={self.network_name} :are supported by this server")
                # TODO: MOTD
                self.reply_numeric(client_data, 422, ":MOTD File is missing")
            case "PING":
                self.reply(client_data, f'PONG {" ".join(command.subcommands)}')
            case "JOIN":
                # TODO: Manage channels and topics?
                # TODO: Ensure starts with pound sign
                if command.subcommands:
                    channels = command.subcommands[0].split(",")
                    for channel in channels:
                        self.reply(client_data, f":{client_data.id()} JOIN {channel}")
                        self.reply_numeric(client_data, 332, f"{channel} :topic")
                        # TODO: actually list users
                        self.reply_numeric(client_data, 353, f"= {channel} :{client_data.nick}")
                        self.reply_numeric(client_data, 366, f"{channel} :End of /NAMES list")
                        # TODO: Handle channel "0" as "part all"
            case "PART":
                channels = command.subcommands[0].split(",")
                for channel in channels:
                    self.broadcast(f":{client_data.id()} PART {channel}")
            case "PRIVMSG":
                # TODO: Only broadcast to clients in the given channel
                channels = command.subcommands[0].split(",")
                for channel in channels:
                    # TODO: Support user messages too?
                    # TODO: Shouldn't send to everyone
                    self.broadcast_others(client_data, f":{client_data.id()} PRIVMSG {channel} :{command.content}")

server = IrcServer()
server.run()
