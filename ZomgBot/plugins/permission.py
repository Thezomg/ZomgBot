from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler

from copy import copy
from itertools import groupby

@Plugin.register(depends=None)
class Permission(Plugin):
    def setup(self):
        self.already_updated = set()
        self.get_config().setdefault("users", {})
        self.get_config().setdefault("groups", {})

    def reset(self):
        self.already_updated = set()

    def add_groups(self, user, groupname, stack=None):
        if stack is None: stack = []
        if groupname in stack:
            return False
        stack.append(groupname)

        cfg = self.get_config()["groups"].setdefault(groupname, {"permissions": [], "parents": []})
        permissions = cfg["permissions"]
        parents = cfg.get("parents", [])

        for p in parents:
            self.add_groups(user, p, stack)
        for p in permissions:
            if '/' in p:
                channel, p = p.split('/', 1)
            else:
                channel = None
            user.add_permission(p, "group:" + groupname, channel)

        stack.pop()

    def refresh_permissions(self, user):
        cfg = self.get_config()
        map(user.remove_permission, copy(user.permissions))
        if user.account in self.parent.parent.config["bot"]["admins"]:
            user.add_permission("*", "config")

        permissions = cfg["users"].get(user.account, {}).get("permissions", [])
        for p in permissions:
            if '/' in p:
                channel, p = p.split('/', 1)
            else:
                channel = None
            user.add_permission(p, "explicit", channel)

        groups = cfg["users"].get(user.account, {}).get("groups", [])
        for g in groups: self.add_groups(user, g)

        self.already_updated.add(user)

    @EventHandler("AuthenticateUser", priority=-5)
    def authenticating(self, event):
        if event.user in self.already_updated or not event.user.account: return
        self.refresh_permissions(event.user)

    @Modifier.command("groupallow", permission="bot.admin.groupallow")
    def cmd_groupallow(self, context):
        assert len(context.args) >= 2
        perms = context.args
        group = perms.pop(0)
        cfg = self.get_config()["groups"].setdefault(group, {"permissions": [], "parents": []})
        n = 0
        for p in perms:
            if context.permission != "global" and not p.startswith(context.channel.name + '/'):
                p = context.channel.name + '/' + p
            if p not in cfg["permissions"]:
               cfg["permissions"].append(p)
        if n:
            self.reset()
            self.save_config()
            return "Added {} permissions to {}".format(n, group)
        else:
            return "Nothing to add."

    @Modifier.command("groupremove", permission="bot.admin.groupremove")
    def cmd_groupremove(self, context):
        assert len(context.args) >= 2
        perms = context.args
        group = perms.pop(0)
        cfg = self.get_config()["groups"].get(group, {"permissions": [], "parents": []})
        n = 0
        for p in perms:
            if context.permission != "global" and not p.startswith(context.channel.name + '/'):
                p = context.channel.name + '/' + p
            if p in cfg["permissions"]:
               del cfg["permissions"][p]
               n += 1
        if n:
            self.reset()
            self.save_config()
            return "Removed {} permissions from {}".format(n, group)
        else:
            return "Nothing to remove."

    @Modifier.command("userallow", permission="bot.admin.userallow")
    def cmd_userallow(self, context):
        assert len(context.args) >= 2
        perms = context.args
        username = perms.pop(0)
        cfg = self.get_config()["users"].setdefault(username, {"permissions": [], "groups": []})
        n = 0
        for p in perms:
            if context.permission != "global" and not p.startswith(context.channel.name + '/'):
                p = context.channel.name + '/' + p
            if p not in cfg["permissions"]:
               cfg["permissions"].append(p)
               n += 1
        if n:
            self.reset()
            self.save_config()
            return "Added {} permissions to {}".format(n, username)
        else:
            return "Nothing to add."

    @Modifier.command("userremove", permission="bot.admin.userremove")
    def cmd_userremove(self, context):
        assert len(context.args) >= 2
        perms = context.args
        username = perms.pop(0)
        cfg = self.get_config()["users"].setdefault(username, {"permissions": [], "groups": []})
        n = 0
        for p in perms:
            if context.permission != "global" and not p.startswith(context.channel.name + '/'):
                p = context.channel.name + '/' + p
            if p in cfg["permissions"]:
               del cfg["permissions"][p]
               n += 1
        if n:
            self.reset()
            self.save_config()
            return "Removed {} permissions from {}".format(n, username)
        else:
            return "Nothing to remove."

    @Modifier.command("deluser", permission="#bot.admin.deluser")
    def cmd_deluser(self, context):
        assert len(context.args) == 1
        username = context.args[0]
        cfg = self.get_config()["users"]
        if username in cfg:
            del cfg[username]
            self.reset()
            self.save_config()
            return "User deleted: {}".format(username)
        else:
            return "No such user: {}".format(username)

    @Modifier.command("delgroup", permission="#bot.admin.delgroup")
    def cmd_delgroup(self, context):
        assert len(context.args) == 1
        group = context.args[0]
        cfg = self.get_config()["groups"]
        if group in cfg:
            del cfg[group]
            self.reset()
            self.save_config()
            return "Group deleted: {}".format(group)
        else:
            return "No such group: {}".format(group)

    @Modifier.command("addtogroup", permission="#bot.admin.addtogroup")
    def cmd_addtogroup(self, context):
        group, username = context.args
        cfg = self.get_config()["users"].setdefault(username, {"permissions": [], "groups": []})
        if group not in cfg["groups"]:
            cfg["groups"].append(group)
            self.reset()
            self.save_config()
            return "Added {} to {}".format(username, group)
        else:
            return "{} is already in {}".format(username, group)

    @Modifier.command("removefromgroup", permission="#bot.admin.removefromgroup")
    def cmd_removefromgroup(self, context):
        group, username = context.args
        cfg = self.get_config()["users"].setdefault(username, {"permissions": [], "groups": []})
        if group in cfg["groups"]:
            cfg["groups"].remove(group)
            self.reset()
            self.save_config()
            return "Removed {} from {}".format(username, group)
        else:
            return "{} is not in {}".format(username, group)
        

