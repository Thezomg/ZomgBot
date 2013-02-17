from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.internet.error import ConnectionDone
from twisted.internet.defer import Deferred

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import signal
import os
import string
from copy import copy
from time import sleep, time
from ircglob import glob

from ZomgBot.plugins import PluginManager, Modifier
from ZomgBot.events import EventDispatcher, Event

class IRCTarget(object):
    def __init__(self, irc, name):
        self.irc = irc
        self.name = name

    def say(self, msg):
        self.irc.msg(self.name, msg)

    def notice(self, msg):
        self.irc.notice(self.name, msg)

    @property
    def display_name(self):
        return self.name
    
    def __str__(self):
        return self.display_name
    
    def __repr__(self):
        return self.display_name

    def __unicode__(self):
        return unicode(self.display_name)


class PermissionSet(object):
    def __init__(self):
        self.permissions = {}

    def add(self, permission, source="?"):
        self.permissions[permission] = source

    def remove(self, permission):
        if permission in self.permissions:
            del self.permissions[permission]

    def has(self, permission):
        if permission in self.permissions: return True
        l = []
        for p in permission.split('.') + ['']:
            if '.'.join(l + ['*']) in self.permissions: return True
            l.append(p)
        return False


class IRCUser(IRCTarget):
    account = None
    username = None
    hostname = None
    status = ''
    prefix = ''

    def __init__(self, irc, name):
        if '!' in name:
            name, self.username, self.hostname = glob.str_to_tuple(name)
        super(IRCUser, self).__init__(irc, name)
        self.channels = set()
        self.permissions = {}
        self.base = self

    @property
    def hostmask(self):
        if not self.hostname or not self.username: return None
        return '{}!{}@{}'.format(self.name, self.username, self.hostname)

    def add_permission(self, permission, source="?", channel=None):
        if isinstance(channel, basestring):
            channel = self.irc.getChannel(channel)
        name = channel.name if channel else "__global__"
        p = self.permissions.setdefault(name, PermissionSet())
        p.add(permission, source)

    def remove_permission(self, permission, channel=None):
        if isinstance(channel, basestring):
            channel = self.irc.getChannel(channel)
        name = channel.name if channel else "__global__"
        p = self.permissions.setdefault(name, PermissionSet())
        p.remove(permission)

    def has_permission(self, permission, channel=None):
        if isinstance(channel, basestring):
            channel = self.irc.getChannel(channel)
        if not permission.startswith('#'):
            if channel and channel.name in self.permissions:
                if self.permissions[channel.name].has(permission): return True
        else:
            permission = permission[1:]
        if "__global__" in self.permissions:
            if self.permissions["__global__"].has(permission): return True
        return False

    def update_info(self, info):
        info = glob.str_to_tuple(info)
        assert self.name == info[0]
        self.username = info[1] or self.username
        self.hostname = info[2] or self.hostname

    def set_account(self, account):
        self.account = account

    def add_channel(self, channel):
        if self.name == self.irc.nickname: return
        self.channels.add(channel)
        channel.getOrCreateUser(self.name)

    def remove_channel(self, channel):
        self.channels.remove(channel)
        del channel.users[self.name.lower()]

    def nick_changed(self, newnick):
        print "*** {} is now known as {}".format(self.name, newnick)
        self.irc.users[newnick.lower()] = self
        del self.irc.users[self.name.lower()]
        for ch in self.channels:
            ch.users[newnick.lower()] = ch.users[self.name.lower()]
            del ch.users[self.name.lower()]
        self.name = newnick


class IRCUserInChannel(object):
    def __init__(self, user):
        self.user = user
        self.status = ''

    @property
    def base(self):
        return self.user

    @property
    def display_name(self):
        return self.prefix + self.user.display_name
    
    @property
    def prefix(self):
        return self.status[:1]

    @property
    def op(self):
        return '@' in self.status

    @property
    def voice(self):
        return '+' in self.status

    def __str__(self):
        return self.display_name

    def __repr__(self):
        return self.display_name

    def __unicode__(self):
        return unicode(self.display_name)
    
    def __getattr__(self, k):
        return getattr(self.user, k)

class IRCChannel(IRCTarget):
    def __init__(self, irc, name):
        super(IRCChannel, self).__init__(irc, name)
        self.users = {}
        self.bans = []
        self._bans = []

    def getUser(self, user):
        nick = self.irc.getNick(user).lower()
        u = self.users.get(nick)
        if u:
            u.update_info(user)
            return u

    def _addUser(self, name):
        user = IRCUserInChannel(self.irc.getOrCreateUser(name))
        if self.irc.getNick(name) != self.irc.nickname: self.users[self.irc.getNick(name).lower()] = user
        return user

    def getOrCreateUser(self, name):
        user = self.getUser(name)
        if user is None:
            user = self._addUser(name)
            user.user.add_channel(self)
        return user

class ZomgBot(irc.IRCClient):
    def _get_nickname(self):
        return self.factory.nickname
    #nickname = property(_get_nickname)

    actually_quit = False

    def __init__(self):
        self.channels = {}
        self.users = {}
        self.capabilities = {}
        self.cap_requests = set()
        self.supports_cap = False
        self.whoisinfo = {}

    # implement capability negotiation from
    # http://ircv3.atheme.org/specification/capability-negotiation-3.1

    # protocol for plugins:
    # handle the "CapList" event and use it to call bot.irc.request_cap(caps...)
    # then handle "CapEnding" where you can check the current caps list in bot.irc.capabilities
    # and (if you're doing SASL for e.g.) return a Deferred that fires when auth is complete

    def connectionMade(self):
        self.events.dispatchEvent(name="Connected", event=None)
        return irc.IRCClient.connectionMade(self)

    def register(self, nickname, hostname='foo', servername='bar'):
        self.sendLine("CAP LS")
        return irc.IRCClient.register(self, nickname, hostname, servername)
    
    def lineReceived(self, line):
        return irc.IRCClient.lineReceived(self, line.decode('utf8'))

    def sendLine(self, line):
        return irc.IRCClient.sendLine(self, line.encode('utf8'))
    
    def _parse_cap(self, cap):
        mod = ''
        while cap[0] in "-~=":
            mod, cap = mod + cap[0], cap[1:]
        if '/' in cap:
            vendor, cap = cap.split('/', 1)
        else:
            vendor = None
        return (cap, mod, vendor)
    
    def request_cap(self, *caps):
        req_list = ' '.join(caps)
        self.cap_requests |= set(caps)
        self.sendLine("CAP REQ :{}".format(' '.join(caps)))

    def end_cap(self):
        def actually_end(result):
            self.sendLine("CAP END")
        r = self.events.dispatchEvent(name="CapEnding", event=None)
        r.addCallback(actually_end)
    
    def irc_CAP(self, prefix, params):
        self.supports_cap = True
        identifier, subcommand, args = params
        args = args.split(' ')
        if subcommand == "LS":
            self.events.dispatchEvent(name="CapList", event=Event(capabilities=args))
            if not self.cap_requests:
                self.sendLine("CAP END")
        elif subcommand == "ACK":
            ack = []
            for cap in args:
                if not cap: continue
                cap, mod, vendor = self._parse_cap(cap)
                # just remove that capability and do nothing else
                if '-' in mod:
                    if cap in self.capabilities:
                        self.events.dispatchEvent(name="CapRemoved", event=Event(cap=cap))
                        del self.capabilities[cap]
                    continue
                if '=' in mod:
                    self.capabilities[cap] = True
                else:
                    self.capabilities[cap] = False
                if '~' in mod:
                    ack.append(cap)
                self.cap_requests.remove(cap)
            if ack:
                self.sendLine("CAP ACK :{}".format(' '.join(ack)))
            if not self.cap_requests:
                self.end_cap()
        elif subcommand == "NAK":
            # this implementation is probably not compliant but it will have to do for now
            for cap in args:
                self.cap_requests.remove(cap)
                self.events.dispatchEvent(name="CapDenied", event=Event(cap=cap))
            if not self.cap_requests:
                self.end_cap()

    def signedOn(self):
        def join_channels(result):
            map(self.join, self.factory.channels)
            for line in self.factory.autorun:
                line = line.format(nick=self.nickname)
                self.sendLine(line)
        r = self.events.dispatchEvent(name="SignedOn", event=None)
        r.addCallback(join_channels)
        print "Signed on as %s" % (self.nickname,)

    def send_message(self, channel, message, length=None):
        message = str(message)
        reactor.callFromThread(self.say, channel, message, length)

    def handleCommand(self, command, prefix, params):
        def really_handle(result):
            if not result: return
            return irc.IRCClient.handleCommand(self, command, prefix, params)
        r = self.events.dispatchEvent(name="IRC." + command, event=Event(prefix=prefix, params=params))
        r.addCallback(really_handle)

    @staticmethod
    def getNick(user):
        return glob.str_to_tuple(user)[0]

    def getUser(self, user):
        name = self.getNick(user.lower())
        u = self.users.get(name)
        if u:
            u.update_info(user)
            return u
    
    def getOrCreateUser(self, user):
        u = self.getUser(user)
        if u is None:
            u = self._addIRCUser(user)
        return u

    def deleteUser(self, user):
        if self.getUser(user):
            del self.users[self.getNick(user.lower())]

    def _addIRCUser(self, user):
        user = self.getNick(user)
        u = IRCUser(self, user)
        if self.getNick(user) != self.nickname: self.users[user.lower()] = u
        return u

    def getChannel(self, channel):
        channel = channel.lower()
        if channel in self.channels:
            return self.channels[channel]
        return None

    def getOrCreateChannel(self, channel):
        ch = self.getChannel(channel)
        if ch is None:
            ch = self._addIRCChannel(channel)
        return ch

    def _addIRCChannel(self, channel):
        channel = channel.lower()
        ch = IRCChannel(self, channel)
        self.channels[channel] = ch
        return ch
    
    def isupport(self, args):
        self.compute_prefix_names()
    
    def compute_prefix_names(self):
        KNOWN_NAMES = {"o": "op", "h": "halfop", "v": "voice"}
        prefixdata = self.supported.getFeature("PREFIX", {"o": ("@",0), "v": ("+",1)}).items()
        op_priority = ([priority for mode, (prefix, priority) in prefixdata if mode == "o"] + [None])[0]
        self.prefixes, self.statuses, self.priority = {}, {}, {}

        for mode, (prefix, priority) in prefixdata:
            name = "?"
            if mode in KNOWN_NAMES:
                name = KNOWN_NAMES[mode]
            elif priority == 0:
                if op_priority == 2:
                    name = "owner"
                else:
                    name = "admin"
            else:
                name = "+" + mode
            self.prefixes[mode] = prefix
            self.statuses[prefix] = name
            self.priority[mode] = priority
            self.priority[prefix] = priority

    def parse_prefixes(self, channel, nick, prefixes=''):
        ch = self.getOrCreateChannel(channel)
        status = []
        for mode, (prefix, priority) in self.supported.getFeature("PREFIX", {"o": ("@",0), "v": ("+",1)}).items():
            if prefix in prefixes + nick:
                nick = nick.replace(prefix, '')
                status.append((prefix, priority))
        if nick == self.nickname: return
        status = ''.join(t[0] for t in sorted(status, key=lambda t: t[1]))
        user = ch.getOrCreateUser(nick)
        user.status = status

    def irc_RPL_NAMREPLY(self, prefix, params):
        users = string.split(params[3])
        for u in users:
            self.parse_prefixes(params[2].lower(), u)

    def irc_RPL_WHOREPLY(self, prefix, params):
        _, channel, username, host, server, nick, status, hg = params
        if nick == self.nickname: return
        hops, gecos = hg.split(' ', 1)
        self.parse_prefixes(channel.lower(), nick, status[1:].replace('*', ''))
        user = self.getOrCreateUser(nick)
        user.username = username
        user.hostname = host

    #def irc_unknown(self, prefix, command, params):
        #print "unknown message from IRCserver. prefix: %s, command: %s, params: %s" % (prefix, command, params)

    # whois stuff
    # The New Way: you do bot.irc.whois("foouser") and get a deferred back, deferred callbacks with a dictionary containing the results

    def whois(self, nickname):
        nickname = nickname.lower()
        defer = Deferred()

        if nickname in self.whoisinfo:
            defers, info = self.whoisinfo[nickname]
            defers.append(defer)
            return defer
        
        info = {}
        self.whoisinfo[nickname] = ([defer], info)

        irc.IRCClient.whois(self, nickname, None)
        return defer

    def irc_RPL_WHOISUSER(self, prefix, params):
        nick, user, host = params[1].lower(), params[2], params[3]
        if nick in self.whoisinfo:
            self.whoisinfo[nick][1].update(user=user, host=host)

    def irc_330(self, prefix, params):
        nick, account = params[1].lower(), params[2]
        if nick in self.whoisinfo:
            self.whoisinfo[nick][1].update(account=account)

    def irc_RPL_ENDOFWHOIS(self, prefix, params):
        nick = params[1].lower()
        if nick in self.whoisinfo:
            defers, info = self.whoisinfo[nick]
            del self.whoisinfo[nick]
            [defer.callback(info) for defer in defers]

    def irc_RPL_BANLIST(self, prefix, params):
        channel, banmask, setter, time = params[1:]
        ch = self.getOrCreateChannel(channel)
        ch._bans.append((banmask, setter, int(time)))

    def irc_RPL_ENDOFBANLIST(self, prefix, params):
        channel = params[1]
        ch = self.getOrCreateChannel(channel)
        ch.bans = ch._bans
        ch._bans = []
        self.events.dispatchEvent(name="BanlistUpdated", event=Event(channel=ch))

    # override our JOIN handling so we can get a user's nick!user@host
    def irc_JOIN(self, prefix, params):
        nick = string.split(prefix,'!')[0]
        channel = params[-1]
        if nick == self.nickname:
            self.joined(channel)
        else:
            self.userJoined(prefix, channel)

    def modeChanged(self, user, channel, _set, modes, args):
        args = list(args)
        if channel.startswith("#"):
            ch = self.getChannel(channel)
            print "%s: mode (%s) %s (%s)" % (str(channel), "+" if _set else "-", modes, ', '.join(map(str,args)))

            if ch:
                for m in modes:
                    arg = args.pop(0)
                    if m in self.prefixes:
                        if arg != self.nickname:
                            u = ch.getOrCreateUser(arg)
                            u.status = u.status.replace(self.prefixes[m], '')
                            if _set:
                                u.status = ''.join(sorted(list(u.status + self.prefixes[m]), key=lambda k: self.priority[k]))
                    elif m == 'b':
                        if _set:
                            ch.bans.append((arg, user, time()))
                        else:
                            rm = [b for b in ch.bans if b[0] == arg]
                            [ch.bans.remove(b) for b in rm]

                    self.events.dispatchEvent(name="ModeSet" if _set else "ModeCleared",
                                              event=Event(channel=ch, user=ch.getOrCreateUser(user), letter=m, param=arg))
            else:
                print "Received mode change for unknown channel {}, possible desync".format(channel)

    def userRenamed(self, oldname, newname):
        self.getOrCreateUser(oldname).nick_changed(newname)
        self.events.dispatchEvent(name="UserChangedNick", event=Event(user=self.getOrCreateUser(newname), old=oldname))

    def userLeftSomehow(self, user, channel):
        user.remove_channel(channel)
        if not user.channels:
            self.events.dispatchEvent(name="StoppedTracking", event=Event(user=user))
            self.deleteUser(user.name)

    def userLeft(self, user, channel):
        ch = self.getOrCreateChannel(channel)
        u = self.getOrCreateUser(user)
        self.events.dispatchEvent(name="UserPartedChannel", event=Event(user=u, channel=ch))
        self.userLeftSomehow(u, ch)

    def userKicked(self, kickee, channel, kicker, message):
        ch = self.getOrCreateChannel(channel)
        kicker = ch.getOrCreateUser(kicker)
        if kickee == self.nickname:
            self.events.dispatchEvent(name="Kicked", event=Event(kicker=kicker, channel=ch, message=message))
        else:
            kickee = ch.getOrCreateUser(kickee)
            self.events.dispatchEvent(name="UserKicked", event=Event(kickee=kickee, kicker=kicker, channel=ch, message=message))
            self.userLeftSomehow(kickee, ch)

    def userJoined(self, user, channel):
        ch = self.getOrCreateChannel(channel)
        self.getOrCreateUser(user).add_channel(ch)
        self.events.dispatchEvent(name="UserJoinedChannel", event=Event(user=ch.getUser(user), channel=ch))
    
    def userQuit(self, user, quitMessage):
        u = self.getOrCreateUser(user)
        self.events.dispatchEvent(name="UserQuit", event=Event(user=u, message=quitMessage))
        map(u.remove_channel, copy(u.channels))
        self.events.dispatchEvent(name="StoppedTracking", event=Event(user=user))
        self.deleteUser(user)

    def joined(self, channel):
        if self.channels.has_key(channel.lower()):
            del self.channels[channel.lower()]

        ch = self._addIRCChannel(channel)
        self.sendLine("WHO :{}".format(channel))
        self.sendLine("MODE {} +b".format(channel))
        self.events.dispatchEvent(name="JoinedChannel", event=ch)
        print "Joined %s" % (channel)

    def privmsg(self, user, channel, msg):
        info = glob.str_to_tuple(user)
        if channel[0] in self.supported.getFeature("CHANTYPES"):
            ch = self.getChannel(channel)
            u = ch.getOrCreateUser(user)
            self.events.dispatchEvent(name="ChannelMsg", event=Event(channel=ch, user=u, message=msg))
            print "%s: <%s> %s" % (channel, u, msg,)
        elif channel == self.nickname:
            self.events.dispatchEvent(name="PrivateMsg", event=Event(user=self.getOrCreateUser(user), message=msg))
            print "<%s> %s" % (info[0], msg)
        else:
            print "Unrecognized target type: {}".format(channel)

    def noticed(self, user, channel, msg):
        info = glob.str_to_tuple(user)
        if channel[0] in self.supported.getFeature("CHANTYPES"):
            ch = self.getChannel(channel)
            u = ch.getOrCreateUser(user)
            self.events.dispatchEvent(name="ChannelNotice", event=Event(channel=ch, user=u, message=msg))
            print "N %s: <%s> %s" % (channel, u, msg,)
        elif channel == self.nickname:
            self.events.dispatchEvent(name="PrivateNotice", event=Event(user=self.getOrCreateUser(user), message=msg))
            print "N <%s> %s" % (info[0], msg)
        # don't bitch about "unrecognized target type" as ircds have a habit of sending us notices to things like "AUTH"

class ZomgBotFactory(protocol.ClientFactory):
    protocol = ZomgBot
    _protocol = None

    @property
    def client(self):
        return self._protocol

    def __init__(self, parent, channels=[], nickname='ZomgBot', username='ZomgBot', autorun=[]):
        self.parent = parent
        self.channels = channels
        self.nickname = nickname
        self.username = username
        self.autorun = autorun

    def buildProtocol(self, addr):
        p = self.protocol()
        p.nickname = self.nickname
        p.username = self.username
        p.factory = self
        p.events = self.parent.events
        #p.init()
        self._protocol = p
        return p

    def clientConnectionLost(self, connector, reason):
        if not self.client.actually_quit:
            print "Lost connection: %s" % reason.getErrorMessage()
            connector.connect()
        else:
            print "Asked to quit, doing so"
            reactor.stop()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason)

class Bot():
    @property
    def irc(self):
        if self._factory:
            return self._factory.client
        else:
            return None

    def stop(self, quit_message="Asked to quit"):
        reactor.callFromThread(self._stop, quit_message)

    def _stop(self, quit_message="Asked to quit"):
        self.plugins.disableAll()
        Modifier.forgetEverything()
        self.irc.actually_quit = True
        self.irc.quit(quit_message)

    _factory = None

    server = None
    port = None
    channel = None
    nickname = None

    def reload(self):
        #self.plugins = PluginManager(self)
        self.config.loadOrCreate()
        self.plugins.disableAll()
        Modifier.forgetEverything()
        self.plugins.load_plugins("ZomgBot.plugins")

    def init(self, cfg):
        self.server = cfg["irc"]["server"]
        self.port =   cfg["irc"]["port"]
        self.channels = cfg["irc"]["channels"]
        self.nickname = cfg["irc"]["nick"]
        self.username = cfg["irc"].get("username", "ZomgBot")
        self.autorun = cfg["irc"].get("autorun", [])

        self.config = cfg

        self.db_engine = create_engine(cfg["bot"]["database"])
        self.sessionmaker = sessionmaker(bind=self.db_engine)

        self.events = EventDispatcher()

        self.plugins = PluginManager(self)
        self.plugins.load_plugins("ZomgBot.plugins")

    def run(self):
        self._factory = ZomgBotFactory(self, self.channels, self.nickname, self.username, self.autorun)
        reactor.connectTCP(self.server, self.port, self._factory)
        reactor.run()

if __name__ == "__main__":
    print "Can't run directly"
