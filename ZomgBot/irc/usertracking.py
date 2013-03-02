from ZomgBot.ircglob import glob
from ZomgBot.events import Event


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

    def reset_permissions(self):
        self.permissions = {}

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


class UsertrackingClient():
    def __init__(self):
        self.channels = {}
        self.users = {}

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
        users = params[3].split()
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
        user.oper = '*' in status
        user.away = status[0] == 'G'

    def irc_354(self, prefix, params):
        _, channel, username, host, server, nick, status, account, gecos = params
        if nick == self.nickname: return
        if account == '0': account = None
        self.parse_prefixes(channel.lower(), nick, status[1:].replace('*', ''))
        user = self.getOrCreateUser(nick)
        user.username = username
        user.hostname = host
        user.account = account
        user.oper = '*' in status
        user.away = status[0] == 'G'

    def irc_JOIN(self, prefix, params):
        nick =  prefix.split('!')[0]
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
