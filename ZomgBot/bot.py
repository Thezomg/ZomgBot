from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.internet.error import ConnectionDone
import signal
import os
import string
from time import sleep
from ircglob import glob
from ZomgBot.plugins import PluginManager, Modifier
from ZomgBot.events import EventDispatcher, Event

class IRCUser():
    def __init__(self, irc, name, op=False, voice=False):
        self.irc = irc
        self.name = name
        self.op = op
        self.voice = voice
    
    def say(self, msg):
        self.irc.say(self.name, msg)

    def __unicode__(self):
        return unicode(self.__repr__())

    def _get_display(self):
        return "%s%s%s" % ( ("@" if self.op else ""), ("+" if self.voice else ""), self.name)
    display = property(_get_display)

    def __repr__(self):
        return "%s%s%s" % ( ("@" if self.op else ""), ("+" if self.voice else ""), self.name)

class IRCChannel():
    def __init__(self, irc, name):
        self.irc = irc
        self.name = name
        self.users = {}

    def getUser(self, name):
        if self.users.has_key(name):
            return self.users[name]
        return None

    def _addUser(self, name):
        user = IRCUser(self.irc, name)
        self.users[name] = user
        return user

    def getOrCreateUser(self, name):
        user = self.getUser(name)
        if user == None:
            user = self._addUser(name)
        return user
    
    def say(self, msg):
        self.irc.say(self.name, msg)

class ZomgBot(irc.IRCClient):
    def _get_nickname(self):
        return self.factory.nickname
    #nickname = property(_get_nickname)

    actually_quit = False

    channels = dict()

    def signedOn(self):
        self.join(self.factory.channel)
        print "Signed on as %s" % (self.nickname,)

    def send_message(self, channel, message, length=None):
        message = str(message)
        reactor.callFromThread(self.say, channel, message, length)

    def _say(self, channel, message, length=None):
        super(ZomgBot, self).say(channel, message, length)
        print "saying %s" % message

    def getChannel(self, channel):
        channel = channel.lower()
        if self.channels.has_key(channel):
            return self.channels[channel]
        return None

    def getOrCreateChannel(self, channel):
        ch = self.getChannel(channel)
        if ch == None:
            ch = self._addIRCChannel(channel)
        return ch

    def _addIRCChannel(self, channel):
        channel = channel.lower()
        ch = IRCChannel(self, channel)
        self.channels[channel] = ch
        ch.users = {}
        return ch

    def irc_RPL_NAMREPLY(self,prefix,params):
        ch = self.getOrCreateChannel(params[2])
        users = string.split(params[3])
        for u in users:
            username = u
            voice = False
            op = False
            if u[0] == '+':
                username = username[1:]
                voice = True
            if u[0] == '@':
                username = username[1:]
                op = True

            user = ch.getOrCreateUser(username)
            user.voice = voice
            user.op = op

    #def irc_unknown(self, prefix, command, params):
        #print "unknown message from IRCserver. prefix: %s, command: %s, params: %s" % (prefix, command, params)

    def modeChanged(self, user, channel, _set, modes, args):
        if channel.startswith("#"):
            ch = self.getChannel(channel)
            print "%s: mode (%s) %s (%s)" % (str(channel), "+" if _set else "-", modes, ', '.join(map(str,args)))

            if ch:
                for i in range(len(modes)):
                    u = ch.getOrCreateUser(args[i])
                    if modes[i] == "o":
                        u.op = _set
                    if mode[i] == "v":
                        u.voice = _set

    def joined(self, channel):
        if self.channels.has_key(channel.lower()):
            del self.channels[channel.lower()]

        ch = self._addIRCChannel(channel)
        self.events.dispatchEvent(name="IJoinChannel", event=ch)
        print "Joined %s" % (channel)

    def privmsg(self, user, channel, msg):
        info = glob.str_to_tuple(user)
        if channel[0] in self.supported.getFeature("chantypes", tuple('#&')):
            ch = self.getChannel(channel)
            u = ch.getOrCreateUser(info[0])
            if msg == "/reload":
                self.factory.parent.reload()
            else:
                self.events.dispatchEvent(name="ChannelMsg", event=Event(channel=ch, user=u, message=msg))
                print "%s: <%s> %s" % (channel, u, msg,)
        elif channel == self.nickname:
            self.events.dispatchEvent(name="PrivateMsg", event=Event(user=IRCUser(self, info[0]), message=msg))
            print "<%s> %s" % (info[0], msg)
        else:
            print "Unrecognized target type: {}".format(channel)

class ZomgBotFactory(protocol.ClientFactory):
    protocol = ZomgBot
    _protocol = None

    @property
    def client(self):
        return self._protocol

    def __init__(self, parent, channel='#llama', nickname='ZomgBot'):
        self.parent = parent
        self.channel = channel
        self.nickname = nickname

    def buildProtocol(self, addr):
        p = self.protocol()
        p.nickname = self.nickname
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
        return self._factory.client

    def stop(self, quit_message="Asked to quit"):
        reactor.callFromThread(self._stop, quit_message)

    def _stop(self, quit_message="Asked to quit"):
        self.irc.actually_quit = True
        self.irc.quit(quit_message)

    _factory = None

    server = None
    port = None
    channel = None
    nickname = None

    def reload(self):
        #self.plugins = PluginManager(self)
        self.plugins.disableAll()
        self.plugins.load_plugins("ZomgBot.plugins")
        Modifier.forgetEverything()

    def init(self, cfg):
        self.server = cfg["irc"]["server"]
        self.port =   cfg["irc"]["port"]
        self.channel = cfg["irc"]["channels"][0]
        self.nickname = cfg["irc"]["nick"]

        self.config = cfg

        self.events = EventDispatcher("fred")

        self.plugins = PluginManager(self)
        self.plugins.load_plugins("ZomgBot.plugins")

    def run(self):
        self._factory = ZomgBotFactory(self, self.channel, self.nickname)
        reactor.connectTCP(self.server, self.port, self._factory)
        reactor.run()

if __name__ == "__main__":
    print "Can't run directly"
