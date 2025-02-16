# pirc
**pirc** is a **minimal, single-instance IRC server** that is written in Python, using only the standard library and a minimum of abstraction.

Note: **pirc does not use or support encryption**, so never use it for anything important!

## Usage
```
python pirc.py <host/IP>[:<port>] [<MOTD file>]
```

Port and MOTD file are optional (default port is 6667). Example: `python pirc.py localhost:1234 motd.txt` or `python pirc.py localhost`.

## Why?
Basically, I wanted a chat server that I could use from old/slow/vintage computers.

Specifically:

* IRC works on vintage computers
* I wanted an IRC server that didn't broadcast users' hostnames by default
* Self-hosting is virtuous
* Discord is huge and slow (at least on my old computer)
* I was just curious how simple an IRC server could be

## Features
* Does not expose connected users' hostnames to everyone on the network (by default!)
* Supports channels (creating, listing, joining, leaving)
* Supports "private" messages (note: not actually private due to there being no encryption!)

## Out-of-scope functionality
* Only supports a single instance
* No encryption
* No user accounts or authentication
* No concept of operators

## TODOs
* Consider implementing topic management

## General IRC Resources
* https://modern.ircdocs.horse/
* https://ircv3.net/specs/extensions/capability-negotiation.html
* http://chi.cs.uchicago.edu/chirc/irc_examples.html
