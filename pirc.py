import re
import selectors
import socket
from enum import Enum

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
                assert isinstance(key.fileobj, socket.socket)
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

    def enumerate_clients(self, excluded: socket.socket|None = None) -> list[tuple[socket.socket, type]]:
        result = []
        for _f, k in self.selector.get_map().items():
            if not (k.fileobj == self.listener or k.fileobj == excluded):
                assert isinstance(k.fileobj, socket.socket)
                result.append((k.fileobj, k.data))
        return result

    def create_client_data(self, client: socket.socket):
        raise NotImplementedError()

    def handle(self, client_data, message: bytes) -> None:
        raise NotImplementedError()

# IRC command parser
command_pattern = r"^(?P<source>:[a-zA-Z0-9@#*_.+!\-]+ )?(?P<command>[A-Z]+)(?P<subcommands>( [a-zA-Z0-9@#*_.+!\-]+)*)( :(?P<content>.*))?$"

class Command:
    def __init__(self, text: str) -> None:
        # Parse message
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
        # TODO: Random nick/user/host by default
        self.nick = "?"
        self.user = "?"
        self.host = "internet"

    def id(self) -> str:
        return f"{self.nick}!{self.user}@{self.host}"

# IRC numeric replies
class Reply(Enum):
    Welcome = 1
    YourHost = 2
    Created = 3
    MyInfo = 4
    ISupport = 5
    ListStart = 321
    List = 322
    ListEnd = 323
    Topic = 332
    NameReply = 353
    EndOfNames = 366
    NoMotd = 422

# Server
class IrcServer(TcpServer):
    def __init__(
            self,
            host="localhost",
            port=1234,
            max_pending_clients=5,
            network_name="pircnet",
            server_name="pirc",
            ):
        super().__init__(host, port, 512, max_pending_clients)
        self.network_name = network_name
        self.server_name = server_name
        self.version = 0.1
        self.channels: dict[str, list[ClientRegistration]] = dict()

    def encode(self, message: str) -> bytes:
        return f"{message}\r\n".encode("utf-8")

    def send_text_each(self, clients: list[ClientRegistration], message: str, excluded: ClientRegistration|None = None) -> None:
        # TODO: If a send fails, disconnect *that* client and not the sender!
        print(f"-->  {message}")
        bytes = self.encode(message)
        for client_data in clients:
            if not client_data == excluded:
                # TODO: This skips logging!
                self.send(client_data.client, bytes)

    def create_client_data(self, client: socket.socket) -> ClientRegistration:
        return ClientRegistration(client)
    
    def handle(self, client_data: ClientRegistration, message: bytes) -> None:
        text = message.decode("utf-8")
        lines = text.strip().split("\r\n")
        for line in lines:
            print(f"<-- {line}")
            self.handle_command(client_data, Command(line))
    
    def reply(self, client_data: ClientRegistration, text: str) -> None:
        self.send_text_each([client_data], text)

    def reply_numeric(self, client_data: ClientRegistration, reply: Reply, text: str) -> None:
        self.reply(client_data, f"{str(reply.value).zfill(3)} {client_data.nick} {text}")

    def channel_get(self, channel: str) -> list[ClientRegistration]:
        if not channel in self.channels:
            self.channels[channel] = []
        return self.channels[channel]

    def handle_command(self, client_data: ClientRegistration, command: Command) -> None:
        match command.command:
            case "CAP":
                if command.subcommands:
                    match command.subcommands[0]:
                        case "LS":
                            self.reply(client_data, "CAP * ACK")
            case "NICK":
                # TODO: Check for collision
                # TODO: Truncate, if needed
                if command.subcommands and len(command.subcommands) >= 1:
                    client_data.nick = command.subcommands[0]
            case "USER":
                if command.subcommands and len(command.subcommands) >= 1:
                    client_data.user = command.subcommands[0]
                    self.reply_numeric(client_data, Reply.Welcome, f":Welcome, {client_data.id()}")
                    self.reply_numeric(client_data, Reply.YourHost, f":Your host is {self.server_name}, running version {self.version}")
                    self.reply_numeric(client_data, Reply.Created, ":This server was created today")
                    self.reply_numeric(client_data, Reply.MyInfo, f"{self.server_name} {self.version}  ")
                    self.reply_numeric(client_data, Reply.ISupport, f"NETWORK={self.network_name} :are supported by this server")
                    # TODO: MOTD
                    self.reply_numeric(client_data, Reply.NoMotd, ":MOTD File is missing")
            case "PING":
                if command.subcommands:
                    self.reply(client_data, f'PONG {" ".join(command.subcommands)}')
            case "JOIN":
                # TODO: Manage topics?
                if command.subcommands:
                    channels = command.subcommands[0].split(",")
                    for channel in channels:
                        # TODO: Handle channel "0" as "part all"
                        if len(channel) >= 1 and channel[0] == "#":
                            clients = self.channel_get(channel)
                            if not client_data in clients:
                                clients.append(client_data)
                                self.send_text_each(clients, f":{client_data.id()} JOIN {channel}")
                                self.reply_numeric(client_data, Reply.Topic, f"{channel} :topic")
                                # TODO: Split nick list, if needed
                                self.reply_numeric(client_data, Reply.NameReply, f"= {channel} :{",".join([c.nick for c in clients])}")
                                self.reply_numeric(client_data, Reply.EndOfNames, f"{channel} :End of /NAMES list")
            # TODO: QUIT message
            case "PART":
                if command.subcommands and len(command.subcommands) >= 1:
                    channels = command.subcommands[0].split(",")
                    for channel in channels:
                        if len(channel) >= 1 and channel[0] == "#" and channel in self.channels and client_data in self.channels[channel]:
                            clients = self.channels[channel]
                            clients.remove(client_data)
                            self.send_text_each([client_data, *clients], f":{client_data.id()} PART {channel}")
                            if len(clients) <= 0:
                                del self.channels[channel]
            case "LIST":
                self.reply_numeric(client_data, Reply.ListStart, "Channel :Users  Name")
                for channel, clients in self.channels.items():
                    self.reply_numeric(client_data, Reply.List, f"{channel} {len(clients)} :")
                self.reply_numeric(client_data, Reply.ListEnd, "End of /LIST")
            case "PRIVMSG":
                if command.subcommands and len(command.subcommands) >= 1:
                    targets = command.subcommands[0].split(",")
                    for target in targets:
                        message = f":{client_data.id()} PRIVMSG {target} :{command.content}"
                        if len(target) >= 1 and target[0] == "#":
                            if target in self.channels and client_data in self.channels[target]:
                                self.send_text_each(self.channels[target], message, client_data)
                        else:
                            for _target_client, target_client_data in filter(lambda t: t[1].nick == target, self.enumerate_clients()):
                                self.send_text_each([target_client_data], message)


server = IrcServer()
server.run()
