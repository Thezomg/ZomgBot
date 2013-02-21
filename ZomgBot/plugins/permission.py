from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

from copy import copy
from itertools import groupby, chain

class User(object):
    parent_name = "groups"

    def __init__(self, groupdict):
        self.permissions = set()
        self.groups = set()
        self.groupdict = groupdict

    @classmethod
    def deserialize(cls, info, groupdict):
        user = cls(groupdict)
        for perm in info.get('permissions', []):
            user.allow(*perm.split('/', 1))
        for group in info.get(cls.parent_name, []):
            channel = None
            if '/' in group:
                group, channel = group.split('/', 1)
            if not group: continue
            user.addtogroup(*group.split('/', 1))
        return user

    def serialize(self):
        return {
                'permissions':     [str(p + '/' + c if c else p) for p, c in self.permissions],
                 self.parent_name: [str(g + '/' + c if c else g) for g, c in self.groups]
               }

    @property
    def empty(self):
        return not self.groups and not self.permissions

    def allow(self, permission, channel=None):
        permission, channel = permission.lower(), channel.lower() if channel else None
        if (permission, channel) in self.permissions: return False
        self.permissions.add((permission, channel))
        return True

    def remove(self, permission, channel=None):
        permission, channel = permission.lower(), channel.lower() if channel else None
        if (permission, channel) not in self.permissions: return False
        self.permissions.remove((permission, channel))
        return True

    def addtogroup(self, group, channel=None):
        group, channel = group.lower(), channel.lower() if channel else None
        if (group, channel) in self.groups: return False
        self.groups.add((group, channel))
        return True

    def removefromgroup(self, group, channel=None):
        group, channel = group.lower(), channel.lower() if channel else None
        if (group, channel) not in self.groups: return False
        self.groups.remove((group, channel))
        return True

    def get_permissions(self, channel=None):
        real_groups = [(self.groupdict.get(g), c) for g, c in self.groups if g in self.groupdict]
        return [(p, channel or c) for p, c in list(self.permissions) +
                                   list(chain.from_iterable(g.get_permissions(c) for g, c in real_groups))
                if channel is None or c is None or c == channel]

class Group(User):
    parent_name = "parents"

@Plugin.register(depends=None)
class Permission(Plugin):
    def setup(self):
        self.already_updated = set()
        self.get_config().setdefault("users", {})
        self.users = {}
        self.groups = {}
        cfg = self.get_config()
        for n, g in cfg.get("groups", {}).items():
            self.groups[n] = Group.deserialize(g, self.groups)

    def reset(self):
        self.already_updated = set()

    def save(self):
        self.reset()
        cfg = self.get_config()
        cfg["users"] = {}
        for name, user in self.users.items():
            if user.empty: continue
            cfg["users"][str(name)] = user.serialize()
        cfg["groups"] = {}
        for name, group in self.groups.items():
            if group.empty: continue
            cfg["groups"][str(name)] = group.serialize()
        self.save_config()

    def get_user(self, name):
        if name not in self.users:
            self.users[name] = User(self.groups)
        return self.users[name]

    def get_group(self, name):
        if name not in self.groups:
            self.groups[name] = Group(self.groups)
        return self.groups[name]

    def refresh_permissions(self, ircuser):
        cfg = self.get_config()
        ircuser.reset_permissions()
        if ircuser.account in self.parent.parent.config["bot"]["admins"]:
            ircuser.add_permission("*", "admin")

        user = cfg["users"].get(ircuser.account, None)
        if not user: return
        u = User.deserialize(user, self.groups)
        self.users[ircuser.account] = u
        for p, c in u.get_permissions():
            ircuser.add_permission(p, "config", c)

        self.already_updated.add(ircuser)

    @EventHandler("AuthenticateUser", priority=-5)
    def authenticating(self, event):
        if event.user in self.already_updated or not event.user.account: return
        self.refresh_permissions(event.user)

    @Modifier.command("userallow", permission="bot.admin.userallow")
    def cmd_userallow(self, context):
        user, perm = map(str, context.args[:2])
        if perm.startswith('#') and context.permission == "global":
            perm = perm[1:]
            if self.get_user(user).allow(perm):
                self.save()
                return "Globally added {} to {}.".format(perm, user)
        else:
            if self.get_user(user).allow(perm, context.channel.name):
                self.save()
                return "Added {} to {} on {}.".format(perm, user, context.channel.name)
        return "Nothing to add."

    @Modifier.command("userremove", permission="bot.admin.userremove")
    def cmd_userremove(self, context):
        user, perm = map(str, context.args[:2])
        if perm.startswith('#') and context.permission == "global":
            perm = perm[1:]
            if self.get_user(user).remove(perm):
                self.save()
                return "Globally removed {} from {}.".format(perm, user)
        else:
            if self.get_user(user).remove(perm, context.channel.name):
                self.save()
                return "Removed {} from {} on {}.".format(perm, user, context.channel.name)
        return "Nothing to remove."

    @Modifier.command("groupallow", permission="bot.admin.groupallow")
    def cmd_groupallow(self, context):
        group, perm = map(str, context.args[:2])
        if perm.startswith('#') and context.permission == "global":
            perm = perm[1:]
            if self.get_group(group).allow(perm):
                self.save()
                return "Globally added {} to {}.".format(perm, group)
        else:
            if self.get_group(group).allow(perm, context.channel.name):
                self.save()
                return "Added {} to {} on {}.".format(perm, group, context.channel.name)
        return "Nothing to add."

    @Modifier.command("groupremove", permission="bot.admin.groupremove")
    def cmd_groupremove(self, context):
        group, perm = map(str, context.args[:2])
        if perm.startswith('#') and context.permission == "global":
            perm = perm[1:]
            if self.get_group(group).remove(perm):
                self.save()
                return "Globally removed {} from {}.".format(perm, group)
        else:
            if self.get_group(group).remove(perm, context.channel.name):
                self.save()
                return "Removed {} from {} on {}.".format(perm, group, context.channel.name)
        return "Nothing to remove."
    
    @Modifier.command("addtogroup", permission="bot.admin.addtogroup")
    def cmd_addtogroup(self, context):
        group, user = map(str, context.args[:2])
        if group.startswith('#') and context.permission == "global":
            group = group[1:]
            if self.get_user(user).addtogroup(group):
                self.save()
                return "Globally added {} to {}.".format(user, group)
        else:
            if self.get_user(user).addtogroup(group, context.channel.name):
                self.save()
                return "Added {} to {} on {}.".format(user, group, context.channel.name)
        return "Nothing to do."
    
    @Modifier.command("removefromgroup", permission="bot.admin.removefromgroup")
    def cmd_removefromgroup(self, context):
        group, user = map(str, context.args[:2])
        if group.startswith('#') and context.permission == "global":
            group = group[1:]
            if self.get_user(user).removefromgroup(group):
                self.save()
                return "Globally removed {} from {}.".format(user, group)
        else:
            if self.get_user(user).removefromgroup(group, context.channel.name):
                self.save()
                return "Removed {} from {} on {}.".format(user, group, context.channel.name)
        return "Nothing to do."
