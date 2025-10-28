#!/usr/bin/env python3

import logging
import random
import re
import selectors
import socket
import string
import sys
import textwrap
import time
from _collections_abc import Iterable
from enum import Enum
from os import environ

# Note: You can set PIRC_LOG_LEVEL=10 to enable DEBUG (10) level logging
log = logging.getLogger("pirc")
logging.basicConfig(level = int(environ.get("PIRC_LOG_LEVEL", logging.INFO)))

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
        log.info(f"Listening on: {self.host}:{self.port}")
        while True:
            # Timeout after 30 seconds to check for periodic tasks
            events = self.selector.select(timeout=30)
            for key, _mask in events:
                assert isinstance(key.fileobj, socket.socket)
                if key.fileobj == self.listener: self.accept()
                else: self.read(key.fileobj, key.data)
            # Perform periodic tasks (like sending PINGs)
            self.periodic_tasks()

    def accept(self) -> None:
        client, _address = self.listener.accept()
        client_data = self.create_client_data(client)
        client.setblocking(False)
        self.selector.register(client, selectors.EVENT_READ, client_data)
    
    def remove_client(self, client: socket.socket) -> None:
        self.selector.unregister(client)
        client.close()
            
    def read(self, client: socket.socket, client_data) -> None:
        try:
            message = client.recv(self.max_message_size)
            if not message: raise ConnectionError()
            self.handle(client_data, message)
        except Exception as e:
            # Treat all errors as disconnections
            log.warning("Exception while handling read", exc_info=e)
            self.remove_client(client)

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

    def periodic_tasks(self) -> None:
        """Override this to perform periodic tasks like sending PINGs"""
        pass

# IRC command parser
command_pattern = r"^(?P<source>:[a-zA-Z0-9@#*_.+!\[\]{}\\|\-]+ )?(?P<command>[A-Za-z]+)(?P<subcommands>( +[a-zA-Z0-9@#*_.+!\[\]{}\\|\-]+)*?)( +:(?P<content>.*))?$"

# Validation patterns
nickname_pattern = r"^[a-zA-Z\[\]\\`_\^\{\|\}][a-zA-Z0-9\[\]\\`_\^\{\|\}\-]{0,29}$"
channel_pattern = r"^[#&][^\s,\x00-\x1f]{1,49}$"

def is_valid_nickname(nick: str) -> bool:
    return bool(re.match(nickname_pattern, nick))

def is_valid_channel(channel: str) -> bool:
    return bool(re.match(channel_pattern, channel))

class Command:
    def __init__(self, text: str) -> None:
        # Parse message
        match = re.match(command_pattern, text)
        if not match: raise SyntaxError("Invalid message received!")
        source = match["source"]
        subcommands = match["subcommands"]
        self.source = source[1:-1] if source else None
        self.command = match["command"].upper()
        self.subcommands = subcommands.split() if subcommands else None
        self.content = match["content"]
    
    def __repr__(self):
        return f"Command: {self.command}, Subcommands: {repr(self.subcommands)}, Content: {self.content}"

# IRC client representation
def random_id() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=7))

def compute_id(nick: str, user: str, host: str) -> str:
    return f"{nick}!{user}@{host}"

class ClientRegistration:
    def __init__(self, client: socket.socket) -> None:
        self.client = client
        self.nick = f"n{random_id()}"
        self.nick_set = False
        self.user = f"u{random_id()}"
        self.host = f"h{random_id()}"
        self.channels = []
        self.last_ping_time = time.time()

    def id(self) -> str:
        return compute_id(self.nick, self.user, self.host)

# IRC numeric replies
class Reply(Enum):
    Welcome = 1
    YourHost = 2
    Created = 3
    MyInfo = 4
    ISupport = 5
    WhoisUser = 311
    WhoisServer = 312
    EndOfWho = 315
    EndOfWhois = 318
    ListStart = 321
    List = 322
    ListEnd = 323
    NoTopicSet = 331
    Topic = 332
    WhoReply = 352
    NameReply = 353
    EndOfNames = 366
    Motd = 372
    MotdStart = 375
    EndOfMotd = 376
    NoSuchNick = 401
    NoSuchChannel = 403
    UnknownCommand = 421
    NoMotd = 422
    ErroneousNickname = 432
    NicknameInUse = 433
    BadChannelName = 479

# Server
class IrcServer(TcpServer):
    def __init__(
            self,
            host="localhost",
            port=1234,
            max_pending_clients=5,
            network_name="pircnet",
            server_name="pirc",
            motd: Iterable[str]=[],
            ):
        super().__init__(host, port, 512, max_pending_clients)
        self.network_name = network_name
        self.server_name = server_name
        self.version = 0.1
        self.channels: dict[str, list[ClientRegistration]] = dict()
        self.topics: dict[str, str] = dict()
        self.users: dict[str, ClientRegistration] = dict()
        self.motd = []
        for line in motd:
            for l in (textwrap.wrap(line) if line else [""]):
                self.motd.append(l)

    def encode(self, message: str) -> bytes:
        return f"{message}\r\n".encode("utf-8")

    def send_text_each(self, clients: Iterable[ClientRegistration], message: str, excluded: ClientRegistration|None = None) -> None:
        log.debug(f"-->  {message}")
        encoded_message = self.encode(message)
        for client_data in clients:
            if not client_data == excluded:
                try:
                    self.send(client_data.client, encoded_message)
                except Exception as e:
                    log.warning("Exception while sending; disconnecting client", exc_info=e)
                    self.remove_client(client_data.client)

    def create_client_data(self, client: socket.socket) -> ClientRegistration:
        client_data = ClientRegistration(client)
        self.users[client_data.nick.lower()] = client_data
        return client_data
    
    def handle(self, client_data: ClientRegistration, message: bytes) -> None:
        text = message.decode("utf-8")
        lines = text.strip().split("\r\n")
        for line in lines:
            log.debug(f"<-- {line}")
            # Skip empty lines
            if not line.strip():
                continue
            try:
                self.handle_command(client_data, Command(line))
            except SyntaxError as e:
                log.warning(f"Failed to parse command from {client_data.id()}: {repr(line)}", exc_info=e)
    
    def reply(self, client_data: ClientRegistration, text: str) -> None:
        self.send_text_each([client_data], text)

    def reply_numeric(self, client_data: ClientRegistration, reply: Reply, text: str) -> None:
        self.reply(client_data, f":{self.server_name} {str(reply.value).zfill(3)} {client_data.nick} {text}")

    def reply_numerics(self, client_data: ClientRegistration, replies: list[tuple[Reply, str]]) -> None:
        for reply, text in replies:
            self.reply_numeric(client_data, reply, text)

    def channel_get(self, channel: str) -> list[ClientRegistration]:
        channel_lower = channel.lower()
        if not channel_lower in self.channels:
            self.channels[channel_lower] = []
        return self.channels[channel_lower]
    
    # Note: Needed a safe way to retrieve members of a channel, even if a channel was just deleted
    def channel_get_members(self, channel: str) -> list[ClientRegistration]:
        channel_lower = channel.lower()
        return self.channels[channel_lower] if channel_lower in self.channels else []

    def leave_channel(self, client_data: ClientRegistration, channel: str):
        channel_lower = channel.lower()
        if channel_lower in self.channels:
            channel_list = self.channels[channel_lower]
            if client_data in channel_list:
                channel_list.remove(client_data)
                if len(channel_list) <= 0:
                    del self.channels[channel_lower]
                    # Clean up topic when channel is empty
                    if channel_lower in self.topics:
                        del self.topics[channel_lower]
        if channel_lower in client_data.channels:
            client_data.channels.remove(channel_lower)

    def remove_client(self, client: socket.socket, reason = "") -> None:
        # Need to also remove from user/channel dictionaries and send QUIT messages
        key = self.selector.get_map().get(client)
        client_data = key.data if key else None
        super().remove_client(client)
        if client_data:
            # Remove from user list
            assert isinstance(client_data, ClientRegistration)
            if client_data.nick.lower() in self.users:
                del self.users[client_data.nick.lower()]
            # Remove from channels
            neighbors = set()
            for channel in client_data.channels:
                if channel in self.channels:
                    self.leave_channel(client_data, channel)
                    neighbors = neighbors.union(self.channel_get_members(channel))
            # Send QUIT updates to interested (i.e. in shared channel) clients
            self.send_text_each(neighbors, f":{client_data.id()} QUIT :Quit: {reason}")
            log.info(f"User disconnected: {client_data.id()}")

    def send_motd(self, client_data: ClientRegistration) -> None:
        if self.motd:
            for i, line in enumerate(self.motd):
                self.reply_numeric(client_data, Reply.MotdStart if i == 0 else Reply.Motd, f":- {line}")
            self.reply_numeric(client_data, Reply.EndOfMotd, ":-")
        else:
            self.reply_numeric(client_data, Reply.NoMotd, ":MOTD File is missing")

    def send_topic(self, client_data: ClientRegistration, channel: str) -> None:
        if channel in self.topics and self.topics[channel]:
            self.reply_numeric(client_data, Reply.Topic, f"{channel} :{self.topics[channel]}")
        else:
            self.reply_numeric(client_data, Reply.NoTopicSet, f"{channel} :No topic is set")

    def periodic_tasks(self) -> None:
        """Send periodic PINGs to clients"""
        current_time = time.time()
        ping_interval = 60  # Send PING every 60 seconds

        for client_socket, client_data in self.enumerate_clients():
            if isinstance(client_data, ClientRegistration):
                if current_time - client_data.last_ping_time >= ping_interval:
                    try:
                        self.reply(client_data, f"PING :{self.server_name}")
                        client_data.last_ping_time = current_time
                        log.debug(f"Sent PING to {client_data.id()}")
                    except Exception as e:
                        log.warning(f"Failed to send PING to {client_data.id()}", exc_info=e)

    def handle_command(self, client_data: ClientRegistration, command: Command) -> None:
        match command.command:
            case "CAP":
                if command.subcommands:
                    match command.subcommands[0]:
                        case "LS":
                            self.reply(client_data, "CAP * ACK")
            case "NICK":
                if command.subcommands and len(command.subcommands) >= 1:
                    nick = command.subcommands[0]
                    if not is_valid_nickname(nick):
                        self.reply_numeric(client_data, Reply.ErroneousNickname, f"{nick} :Erroneous nickname")
                    elif nick.lower() in self.users:
                        self.reply_numeric(client_data, Reply.NicknameInUse, ":Nickname already in use")
                    else:
                        old_nick = client_data.nick
                        if old_nick.lower() in self.users: del self.users[old_nick.lower()]
                        client_data.nick = nick
                        self.users[nick.lower()] = client_data
                        if client_data.nick_set:
                            # Find all users in shared channels to notify them of the nick change
                            neighbors = set([client_data])  # Include self
                            for channel in client_data.channels:
                                if channel in self.channels:
                                    neighbors.update(self.channels[channel])
                            self.send_text_each(neighbors, f":{compute_id(old_nick, client_data.user, client_data.host)} NICK {nick}")
                        client_data.nick_set = True
            case "USER":
                if command.subcommands and len(command.subcommands) >= 1:
                    client_data.user = command.subcommands[0]
                    self.reply_numerics(client_data, [
                        (Reply.Welcome,     f":Welcome, {client_data.id()}"),
                        (Reply.YourHost,    f":Your host is {self.server_name}, running version {self.version}"),
                        (Reply.Created,     ":This server was created today"),
                        (Reply.MyInfo,      f"{self.server_name} {self.version}  "),
                        (Reply.ISupport,    f"NETWORK={self.network_name} :are supported by this server"),
                    ])
                    self.send_motd(client_data)
                    log.info(f"New user connected: {client_data.id()}")
            case "MOTD":
                self.send_motd(client_data)
            case "PING":
                # Handle both "PING :token" and "PING token" formats
                # Proper IRC format: PONG <server> :token
                if command.content:
                    self.reply(client_data, f':{self.server_name} PONG {self.server_name} :{command.content}')
                elif command.subcommands:
                    token = " ".join(command.subcommands)
                    self.reply(client_data, f':{self.server_name} PONG {self.server_name} :{token}')
            case "PONG":
                # Client responded to our PING - update last activity time
                client_data.last_ping_time = time.time()
            case "JOIN":
                if command.subcommands:
                    channels = command.subcommands[0].split(",")
                    for channel in channels:
                        if not is_valid_channel(channel):
                            self.reply_numeric(client_data, Reply.BadChannelName, f"{channel} :Bad channel name")
                        else:
                            channel_lower = channel.lower()
                            if channel_lower in client_data.channels:
                                # Already in channel, just send the current state
                                clients = self.channel_get(channel_lower)
                                self.send_topic(client_data, channel_lower)
                                self.reply_numerics(client_data, [
                                    (Reply.NameReply, f"= {channel_lower} :{' '.join([c.nick for c in clients])}"),
                                    (Reply.EndOfNames, f"{channel_lower} :End of /NAMES list"),
                                ])
                            else:
                                # Join the channel
                                client_data.channels.append(channel_lower)
                                clients = self.channel_get(channel_lower)
                                clients.append(client_data)
                                self.send_text_each(clients, f":{client_data.id()} JOIN {channel_lower}")
                                # TODO: Split nick list, if needed
                                self.send_topic(client_data, channel_lower)
                                self.reply_numerics(client_data, [
                                    (Reply.NameReply, f"= {channel_lower} :{' '.join([c.nick for c in clients])}"),
                                    (Reply.EndOfNames, f"{channel_lower} :End of /NAMES list"),
                                ])
            case "QUIT":
                self.remove_client(client_data.client, command.content if command.content else "")
            case "PART":
                if command.subcommands and len(command.subcommands) >= 1:
                    channels = command.subcommands[0].split(",")
                    for channel in channels:
                        channel_lower = channel.lower()
                        if len(channel) >= 1 and channel[0] == "#" and channel_lower in self.channels and channel_lower in client_data.channels:
                            self.leave_channel(client_data, channel_lower)
                            self.send_text_each([client_data, *self.channel_get_members(channel_lower)], f":{client_data.id()} PART {channel_lower}")
            case "LIST":
                self.reply_numeric(client_data, Reply.ListStart, "Channel :Users  Name")
                for channel, clients in self.channels.items():
                    self.reply_numeric(client_data, Reply.List, f"{channel} {len(clients)} :")
                self.reply_numeric(client_data, Reply.ListEnd, "End of /LIST")
            case "WHOIS":
                if command.subcommands and len(command.subcommands) >= 1:
                    target_nick = command.subcommands[0]
                    if target_nick.lower() in self.users:
                        target_user = self.users[target_nick.lower()]
                        self.reply_numerics(client_data, [
                            (Reply.WhoisUser, f"{target_user.nick} {target_user.user} {target_user.host} * :User"),
                            (Reply.WhoisServer, f"{target_user.nick} {self.server_name} :{self.network_name}"),
                            (Reply.EndOfWhois, f"{target_nick} :End of /WHOIS list"),
                        ])
                    else:
                        self.reply_numerics(client_data, [
                            (Reply.NoSuchNick, f"{target_nick} :No such nick/channel"),
                            (Reply.EndOfWhois, f"{target_nick} :End of /WHOIS list"),
                        ])
            case "TOPIC":
                if command.subcommands and len(command.subcommands) >= 1:
                    channel = command.subcommands[0]
                    channel_lower = channel.lower()
                    if channel_lower not in self.channels:
                        self.reply_numeric(client_data, Reply.NoSuchChannel, f"{channel} :No such channel")
                    elif channel_lower not in client_data.channels:
                        self.reply_numeric(client_data, Reply.NoSuchChannel, f"{channel} :You're not on that channel")
                    elif command.content is not None:
                        # Set topic
                        self.topics[channel_lower] = command.content
                        # Broadcast to all users in channel
                        self.send_text_each(self.channels[channel_lower], f":{client_data.id()} TOPIC {channel_lower} :{command.content}")
                    else:
                        # View topic
                        self.send_topic(client_data, channel_lower)
            case "PRIVMSG":
                if command.subcommands and len(command.subcommands) >= 1:
                    targets = command.subcommands[0].split(",")
                    for target in targets:
                        if len(target) >= 1 and target[0] == "#":
                            target_lower = target.lower()
                            if target_lower in self.channels and client_data in self.channels[target_lower]:
                                message = f":{client_data.id()} PRIVMSG {target_lower} :{command.content}"
                                self.send_text_each(self.channels[target_lower], message, client_data)
                        else:
                            if target.lower() in self.users:
                                message = f":{client_data.id()} PRIVMSG {target} :{command.content}"
                                self.send_text_each([self.users[target.lower()]], message)
                            else:
                                self.reply_numeric(client_data, Reply.NoSuchNick, f"{target} :No such nick/channel")
            case "MODE":
                # MODE command - for now, just acknowledge without actually applying modes
                if command.subcommands and len(command.subcommands) >= 1:
                    target = command.subcommands[0]
                    # If querying channel modes, return simple +nt
                    if len(target) >= 1 and target[0] == "#":
                        channel_lower = target.lower()
                        if channel_lower in self.channels:
                            self.reply(client_data, f":{self.server_name} 324 {client_data.nick} {channel_lower} +nt")
                    # Otherwise silently ignore mode changes (no error)
            case "WHO":
                # WHO command - return info about users in a channel or matching a pattern
                if command.subcommands and len(command.subcommands) >= 1:
                    target = command.subcommands[0]
                    if len(target) >= 1 and target[0] == "#":
                        # WHO for channel
                        channel_lower = target.lower()
                        if channel_lower in self.channels:
                            for user in self.channels[channel_lower]:
                                # Format: <channel> <user> <host> <server> <nick> <H|G> :<hopcount> <realname>
                                self.reply_numeric(client_data, Reply.WhoReply,
                                    f"{channel_lower} {user.user} {user.host} {self.server_name} {user.nick} H :0 User")
                        self.reply_numeric(client_data, Reply.EndOfWho, f"{target} :End of /WHO list")
                    else:
                        # WHO for specific user
                        if target.lower() in self.users:
                            user = self.users[target.lower()]
                            # Find a channel they're in (if any)
                            channel = user.channels[0] if user.channels else "*"
                            self.reply_numeric(client_data, Reply.WhoReply,
                                f"{channel} {user.user} {user.host} {self.server_name} {user.nick} H :0 User")
                        self.reply_numeric(client_data, Reply.EndOfWho, f"{target} :End of /WHO list")
            case _:
                # Unknown command
                self.reply_numeric(client_data, Reply.UnknownCommand, f"{command.command} :Unknown command")

def print_usage():
    print(f"\nUSAGE: {sys.argv[0]} <host/IP>[:<port>] [MOTD file]\n")

if len(sys.argv) <= 1 or sys.argv[1] == "--help":
    print_usage()
    exit(0)

motd = []
if len(sys.argv) >= 3:
    with open(sys.argv[2]) as f:
        motd = f.read().splitlines()

bind_info = re.match(r"^(?P<host>[^:]*?)(:(?P<port>[0-9]+))?$", sys.argv[1])
if (not bind_info):
    print(f"ERROR: couldn't parse bind info: \"{sys.argv[1]}\"")
    print_usage()
    exit(-1)

server = IrcServer(host=bind_info["host"], port=int(bind_info["port"] or 6667), motd=motd)
try:
    server.run()
except KeyboardInterrupt:
    log.info("Server shutting down...")
    exit(0)
