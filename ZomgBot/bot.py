from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.internet.defer import Deferred
from twisted.internet.error import ConnectionDone
from twisted.internet.task import LoopingCall

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

from ZomgBot.irc.usertracking import IRCTarget, IRCChannel, IRCUser, IRCUserInChannel, UsertrackingClient

class ZomgBot(UsertrackingClient, irc.IRCClient):
    def _get_nickname(self):
        return self.factory.nickname
    #nickname = property(_get_nickname)

    actually_quit = False

    def __init__(self):
        UsertrackingClient.__init__(self)
        self.capabilities = {}
        self.cap_requests = set()
        self.supports_cap = False
        self.whoisinfo = {}
        self.who_queue = []

    # implement capability negotiation from
    # http://ircv3.atheme.org/specification/capability-negotiation-3.1

    # protocol for plugins:
    # handle the "CapList" event and use it to call bot.irc.request_cap(caps...)
    # then handle "CapEnding" where you can check the current caps list in bot.irc.capabilities
    # and (if you're doing SASL for e.g.) return a Deferred that fires when auth is complete

    def connectionMade(self):
        self.events.dispatchEvent(name="Connected", event=None)
        self.who_cycle = LoopingCall(self.who_next_channel)
        self.who_cycle.start(10, False)
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

    def supports_whox(self):
        return self.supported.hasFeature("WHOX")

    def who(self, channel):
        if self.supports_whox():
            self.sendLine("WHO {} %cuhsnfar".format(channel))
        else:
            self.sendLine("WHO {}".format(channel))

    def who_next_channel(self):
        if not self.who_queue:
            self.who_queue = [str(c.name) for c in self.channels.values()]
        if self.who_queue:
            c = self.who_queue.pop(0)
            self.who(c)

    def joined(self, channel):
        if self.channels.has_key(channel.lower()):
            del self.channels[channel.lower()]

        ch = self._addIRCChannel(channel)
        self.who(channel)
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
