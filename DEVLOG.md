# PIRC - Python IRC Server Development Log

## Overview

PIRC is a lightweight IRC server implementation written in Python 3. It's designed to be simple, easy to understand, and suitable for small networks, BBS systems, and testing environments.

**Version:** 0.1
**Language:** Python 3.11+
**Architecture:** Single-threaded, select-based event loop

## Features

### Core IRC Protocol Support

#### User Management
- Case-insensitive nicknames (RFC compliant)
- Automatic client registration (NICK/USER)
- Random default nicknames if not specified
- Nickname validation (1-30 chars, proper format)
- Collision detection for duplicate nicknames

#### Channel Management
- Case-insensitive channel names (RFC compliant)
- Multiple users per channel
- Channel topic support (view and set)
- Automatic channel creation on JOIN
- Automatic channel cleanup when empty
- Channel name validation (#/& prefix required)

#### Messaging
- Private messages (PRIVMSG) to users and channels
- Channel broadcasting (excludes sender)
- Error replies for non-existent targets
- Action messages (/me via CTCP ACTION)

#### Connection Management
- Non-blocking socket I/O with selectors
- Graceful connection cleanup
- QUIT message broadcasting to shared channels
- Periodic PING/PONG keepalive (60 second interval)
- Proper handling of client disconnections

### Supported IRC Commands

| Command | Status | Description |
|---------|--------|-------------|
| NICK | ✅ Full | Set/change nickname with validation |
| USER | ✅ Full | Complete user registration |
| JOIN | ✅ Full | Join channels with validation |
| PART | ✅ Full | Leave channels |
| QUIT | ✅ Full | Disconnect with optional message |
| PRIVMSG | ✅ Full | Send messages to users/channels |
| PING | ✅ Full | Keepalive from client |
| PONG | ✅ Full | Response to server PING |
| MOTD | ✅ Full | Display Message of the Day |
| WHOIS | ✅ Full | Get user information |
| TOPIC | ✅ Full | View/set channel topic |
| LIST | ✅ Full | List all channels |
| WHO | ✅ Basic | List users in channel/query user |
| MODE | ⚠️ Stub | Returns +nt for channels, ignores changes |
| CAP | ⚠️ Stub | Acknowledges capability negotiation |

### IRC Numeric Replies Implemented

- 001-005: Welcome sequence and server info
- 311-312: WHOIS user and server info
- 315: End of WHO list
- 318: End of WHOIS
- 321-323: LIST responses
- 331-332: Topic messages
- 352-353: WHO and NAMES replies
- 366: End of NAMES
- 372-376: MOTD messages
- 401: No such nick/channel
- 403: No such channel
- 421: Unknown command
- 422: No MOTD file
- 432: Erroneous nickname
- 433: Nickname in use
- 479: Bad channel name

## Recent Improvements (October 2025)

### Protocol Compliance
1. **Case-insensitive nicknames and channels** - Proper IRC RFC compliance
2. **Command parsing improvements** - Handles multiple spaces, mixed case
3. **PING/PONG format fixes** - Proper IRC format: `:server PONG server :token`
4. **Numeric reply prefixes** - Added server prefix to all numeric replies

### New Commands
1. **WHOIS** - Full implementation with user/server info
2. **TOPIC** - View and set channel topics with broadcasting
3. **WHO** - Basic implementation for channel and user queries
4. **MODE** - Stub implementation to prevent errors
5. **Unknown command handling** - Sends 421 error instead of silent ignore

### Robustness Improvements
1. **Parse error handling** - Invalid commands no longer disconnect clients
2. **Empty line handling** - Skips blank lines in input
3. **Graceful shutdown** - Ctrl-C exits cleanly without traceback
4. **NICK change broadcasting** - All users in shared channels notified
5. **Re-join handling** - Gracefully handles joining already-joined channels
6. **Built-in shadowing fixes** - Renamed `bytes` and `list` variables

### Validation
1. **Nickname validation** - RFC-compliant format, length checks
2. **Channel name validation** - Proper prefix and character requirements
3. **Error messages** - Proper IRC error codes for validation failures

### Bug Fixes
1. **NameReply order** - Fixed to Topic → NameReply → EndOfNames
2. **Space-separated user lists** - Changed from commas to spaces
3. **PRIVMSG error handling** - Now sends 401 for non-existent users
4. **Channel cleanup** - Topics deleted when channels become empty
5. **PONG response tracking** - Updates keepalive timestamp

## Architecture

### Class Structure

```
TcpServer (Generic TCP server base)
├── run() - Main event loop with select()
├── accept() - Handle new connections
├── read() - Read from client sockets
└── periodic_tasks() - Override for periodic operations

IrcServer (IRC protocol implementation)
├── handle_command() - Command dispatcher
├── send_motd() - Send MOTD to client
├── send_topic() - Send channel topic
├── periodic_tasks() - Send PING keepalives
└── reply_numeric() - Send IRC numeric replies

ClientRegistration (Per-client state)
├── client: socket
├── nick: str
├── user: str
├── host: str
├── channels: list[str]
└── last_ping_time: float
```

### Data Structures

- `self.channels: dict[str, list[ClientRegistration]]` - Channel membership
- `self.topics: dict[str, str]` - Channel topics (lowercase keys)
- `self.users: dict[str, ClientRegistration]` - Nickname lookup (lowercase keys)

### Message Flow

1. Client connects → `accept()` → `create_client_data()`
2. Data arrives → `read()` → `handle()`
3. Parse lines → `Command()` → `handle_command()`
4. Execute command → `reply()` / `send_text_each()`
5. Periodic timer → `periodic_tasks()` → send PING

## Usage

### Starting the Server

```bash
# Basic usage
./pirc.py <host>:<port> [motd_file]

# Examples
./pirc.py 0.0.0.0:6667                    # Listen on all interfaces
./pirc.py 192.168.1.100:8888              # Specific IP
./pirc.py localhost:6667 motd.txt         # With MOTD file
```

### Debug Logging

```bash
# Enable DEBUG level logging
PIRC_LOG_LEVEL=10 ./pirc.py 0.0.0.0:6667

# Log levels
# 10 = DEBUG (shows all PING/PONG, command parsing)
# 20 = INFO (connection events, default)
# 30 = WARNING (errors, disconnections)
```

### Signal Handling

- **Ctrl-C** - Graceful shutdown with log message
- All connections closed cleanly

## Client Compatibility

### Tested Clients

| Client | Status | Notes |
|--------|--------|-------|
| zirc (ARexx) | ✅ Full | Amiga BBS IRC client |
| HexChat | ✅ Full | Modern GUI client |
| irssi | ⚠️ Untested | Should work |
| WeeChat | ⚠️ Untested | Should work |

### Known Client Issues

- **HexChat** - Requires proper PING format (`:server PONG server :token`)
- **zirc** - More lenient, handles most variations

## Limitations & Future Enhancements

### Current Limitations

1. **No authentication** - Anyone can connect
2. **No channel operators** - No +o, kick, ban, etc.
3. **No channel modes** - MODE command is a stub
4. **No services** - No NickServ, ChanServ, etc.
5. **No SSL/TLS** - Plaintext only
6. **No server-to-server** - Single server only
7. **No IRCv3** - Basic RFC 1459 implementation
8. **No flood protection** - No rate limiting
9. **No channel limits** - Unlimited users per channel
10. **No persistent state** - Everything lost on restart

### Potential Enhancements

**High Priority:**
- SSL/TLS support
- Basic channel operator commands (KICK, BAN)
- User modes (+i, +w, etc.)
- Channel modes (+t, +n, +m, etc.)
- Away status (AWAY command)

**Medium Priority:**
- ISON command (check if users online)
- USERHOST command
- IRCv3 capability negotiation
- Message tags
- SASL authentication

**Low Priority:**
- Server-to-server linking
- Services integration
- Persistent channels
- Channel registration
- Logging system

## File Structure

```
pirc/
├── pirc.py           # Main server implementation
├── DEVLOG.md         # This file
└── ergo.motd         # Example MOTD file
```

## Development Notes

### Code Style
- Python 3.11+ (uses match/case statements)
- Type hints used throughout
- Logging for debugging and monitoring
- RFC 1459 IRC protocol reference

### Testing
- Test with multiple simultaneous clients
- Test all commands from different clients
- Check PING/PONG with debug logging
- Verify case-insensitive nickname/channel behavior
- Test edge cases (empty input, long messages, etc.)

### Performance
- Single-threaded design suitable for ~50-100 users
- Non-blocking I/O prevents one slow client from blocking others
- 512 byte message limit (IRC standard)
- 30 second select timeout for periodic tasks

## Contributing

When adding new features:
1. Follow existing code style
2. Add appropriate IRC numeric replies to `Reply` enum
3. Update command handler in `handle_command()`
4. Test with multiple clients (zirc and HexChat)
5. Update this DEVLOG with changes
6. Consider RFC compliance

## References

- [RFC 1459](https://tools.ietf.org/html/rfc1459) - Internet Relay Chat Protocol
- [RFC 2812](https://tools.ietf.org/html/rfc2812) - IRC: Client Protocol
- [Modern IRC Documentation](https://modern.ircdocs.horse/) - Up-to-date reference
- [IRCv3 Specifications](https://ircv3.net/) - Modern extensions

## License

(Add license information here)

---

**Last Updated:** October 28, 2025
**Server Version:** 0.1
