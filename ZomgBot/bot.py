from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.internet.error import ConnectionDone
import signal
import os
import string
from copy import copy
from time import sleep
from ircglob import glob
from ZomgBot.plugins import PluginManager, Modifier
from ZomgBot.events import EventDispatcher, Event

class IRCTarget(object):
    def __init__(self, irc, name):
        self.irc = irc
        self.name = name

    def say(self, msg):
        self.irc.say(self.name, msg)

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

class IRCUser(IRCTarget):
    account = None
    username = None
    hostname = None

    def __init__(self, irc, name):
        if '!' in name:
            name, self.username, self.hostname = glob.str_to_tuple(name)[0]
        super(IRCUser, self).__init__(irc, name)
        self.channels = set()
        self.permissions = set()
        self.perms_source = {}

    def add_permission(self, permission, source="?"):
        self.permissions.add(permission)
        self.perms_source[permission] = source
        print "({}): I get permission {} from {}".format(self.name, permission, source)

    def remove_permission(self, permission):
        if permission not in self.permissions: return
        self.permissions.remove(permission)
        del self.perms_source[permission]

    def has_permission(self, permission):
        if permission in self.permissions: return True
        l = []
        for p in permission.split('.') + ['']:  # extra empty string because the last generated string is ignored
            if '.'.join(l + ['*']) in self.permissions: return True
            l.append(p)
        return False
    
    def why(self, permission):
        if permission in self.permissions: return self.perms_source[permission]
        l = []
        for p in permission.split('.') + ['']:  # extra empty string because the last generated string is ignored
            if '.'.join(l + ['*']) in self.permissions: return self.perms_source['.'.join(l + ['*'])]
            l.append(p)
        return "-"

    def set_account(self, account):
        self.account = account

    def add_channel(self, channel):
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
        print "updated nick in {} channels: {}".format(len(self.channels), ', '.join(list(n.name for n in self.channels)))
        self.name = newnick


class IRCUserInChannel(object):
    def __init__(self, user):
        self.user = user
        self.op = False
        self.voice = False

    @property
    def display_name(self):
        return self.prefix + self.user.display_name
    
    @property
    def prefix(self):
        if self.op: return '@'
        if self.voice: return '+'
        return ''

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

    def getUser(self, name):
        if self.users.has_key(name):
            return self.users[name]
        return None

    def _addUser(self, name):
        user = IRCUserInChannel(self.irc.getOrCreateUser(name))
        self.users[name] = user
        return user

    def getOrCreateUser(self, name):
        user = self.getUser(name)
        if user is None:
            user = self._addUser(name)
            user.user.add_channel(self)
        print self.getUser(name)
        return user

class ZomgBot(irc.IRCClient):
    def _get_nickname(self):
        return self.factory.nickname
    #nickname = property(_get_nickname)

    actually_quit = False

    def __init__(self):
        self.channels = {}
        self.users = {}

    def signedOn(self):
        self.join(self.factory.channel)
        print "Signed on as %s" % (self.nickname,)

    def send_message(self, channel, message, length=None):
        message = str(message)
        reactor.callFromThread(self.say, channel, message, length)

    @staticmethod
    def getNick(user):
        return glob.str_to_tuple(user)[0]

    def getUser(self, user):
        user = self.getNick(user.lower())
        if user in self.users:
            return self.users[user]
        return None
    
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
        self.users[user.lower()] = u
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
            print "{} {} {}".format(voice, op, user)

    #def irc_unknown(self, prefix, command, params):
        #print "unknown message from IRCserver. prefix: %s, command: %s, params: %s" % (prefix, command, params)

    def irc_330(self, prefix, params):
        self.events.dispatchEvent(name="WhoisAccount", event=Event(user=self.getOrCreateUser(params[1]), account=params[2]))

    def irc_RPL_ENDOFWHOIS(self, prefix, params):
        self.events.dispatchEvent(name="WhoisEnd", event=Event(user=self.getOrCreateUser(params[1])))

    def modeChanged(self, user, channel, _set, modes, args):
        if channel.startswith("#"):
            ch = self.getChannel(channel)
            print "%s: mode (%s) %s (%s)" % (str(channel), "+" if _set else "-", modes, ', '.join(map(str,args)))

            if ch:
                for i in range(len(modes)):
                    u = ch.getOrCreateUser(args[i])
                    if modes[i] == "o":
                        u.op = _set
                    if modes[i] == "v":
                        u.voice = _set

    def userRenamed(self, oldname, newname):
        print oldname, newname
        self.getOrCreateUser(oldname).nick_changed(newname)

    def userLeft(self, user, channel):
        ch = self.getOrCreateChannel(channel)
        u = self.getOrCreateUser(user)
        u.remove_channel(ch)
        if not u.channels:
            self.deleteUser(user)

    def userJoined(self, user, channel):
        ch = self.getOrCreateChannel(channel)
        self.getOrCreateUser(user).add_channel(ch)
    
    def userQuit(self, user, quitMessage):
        u = self.getOrCreateUser(user)
        map(u.remove_channel, copy(u.channels))
        self.deleteUser(user)

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
        self.plugins.disableAll()
        Modifier.forgetEverything()
        self.plugins.load_plugins("ZomgBot.plugins")

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
