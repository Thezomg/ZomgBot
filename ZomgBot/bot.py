from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.internet.error import ConnectionDone
import signal
import os
from ircglob import glob
import string
from ZomgBot.plugins.jsockplugin import JSockPlugin
from time import sleep

class IRCUser():
    def __init__(self, name, op=False, voice=False):
        self.name = name
        self.op = op
        self.voice = voice

    def __unicode__(self):
        return unicode(self.__repr__())

    def _get_display(self):
        return "%s%s%s" % ( ("@" if self.op else ""), ("+" if self.voice else ""), self.name)
    display = property(_get_display)

    def __repr__(self):
        return "%s%s%s" % ( ("@" if self.op else ""), ("+" if self.voice else ""), self.name)

class IRCChannel():
    def __init__(self, name):
        self.name = name
        self.users = {}

    def getUser(self, name):
        if self.users.has_key(name):
            return self.users[name]
        return None

    def _addUser(self, name):
        user = IRCUser(name)
        self.users[name] = user
        return user

    def getOrCreateUser(self, name):
        user = self.getUser(name)
        if user == None:
            user = self._addUser(name)
        return user

class ZomgBot(irc.IRCClient):
    def _get_nickname(self):
        return self.factory.nickname
    nickname = property(_get_nickname)

    channels = dict()
    jsock = None

    def signedOn(self):
        self.jsock = JSockPlugin(self)
        self.jsock.start()
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
        ch = IRCChannel(channel)
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
                    u = ch.getOrCreate(args[i])
                    if modes[i] == "o":
                        u.op = _set
                    if mode[i] == "v":
                        u.voice = _set

    def joined(self, channel):
        if self.channels.has_key(channel.lower()):
            del self.channels[channel.lower()]

        self._addIRCChannel(channel)
        print "Joined %s" % (channel)

    def privmsg(self, user, channel, msg):
        info = glob.str_to_tuple(user)
        ch = self.getChannel(channel)
        u = ch.getOrCreateUser(info[0])
        print "%s: <%s> %s" % (channel, u, msg,)


class ZomgBotFactory(protocol.ClientFactory):
    protocol = ZomgBot
    _protocol = None
    @property
    def client(self):
        return self._protocol

    def __init__(self, channel='#llama', nickname='ZomgBot'):
        self.channel = channel
        self.nickname = nickname

    def buildProtocol(self, addr):
        p = self.protocol()
        p.factory = self
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
        self.irc.jsock.stop()

    _factory = None

    server = None
    port = None
    channel = None
    nickname = None

    def init(self, server, port, channel, nickname):
        self.server = server
        self.port = port
        self.channel = channel
        self.nickname = nickname

    def run(self):
        self._factory = ZomgBotFactory(self.channel, self.nickname)
        reactor.connectTCP(self.server, self.port, self._factory)
        reactor.run()

if __name__ == "__main__":
    print "Can't run directly"
