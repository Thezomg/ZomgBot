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
        for p in perms:
            if context.permission != "global" and not p.startswith(context.channel.name + '/'):
                p = context.channel.name + '/' + p
            if p not in cfg["permissions"]:
               cfg["permissions"].append(p)
        self.reset()
        self.save_config()

    @Modifier.command("groupremove", permission="bot.admin.groupremove")
    def cmd_groupremove(self, context):
        assert len(context.args) >= 2
        perms = context.args
        group = perms.pop(0)
        cfg = self.get_config()["groups"].get(group, {"permissions": [], "parents": []})
        for p in perms:
            if context.permission != "global" and not p.startswith(context.channel.name + '/'):
                p = context.channel.name + '/' + p
            if p in cfg["permissions"]:
               del cfg["permissions"][p]
        self.reset()
        self.save_config()

    @Modifier.command("userallow", permission="bot.admin.userallow")
    def cmd_userallow(self, context):
        assert len(context.args) >= 2
        perms = context.args
        username = perms.pop(0)
        cfg = self.get_config()["users"].setdefault(username, {"permissions": [], "groups": []})
        for p in perms:
            if context.permission != "global" and not p.startswith(context.channel.name + '/'):
                p = context.channel.name + '/' + p
            if p not in cfg["permissions"]:
               cfg["permissions"].append(p)
        self.reset()
        self.save_config()

    @Modifier.command("userremove", permission="bot.admin.userremove")
    def cmd_userremove(self, context):
        assert len(context.args) >= 2
        perms = context.args
        username = perms.pop(0)
        cfg = self.get_config()["users"].setdefault(username, {"permissions": [], "groups": []})
        for p in perms:
            if context.permission != "global" and not p.startswith(context.channel.name + '/'):
                p = context.channel.name + '/' + p
            if p in cfg["permissions"]:
               del cfg["permissions"][p]
        self.reset()
        self.save_config()

    @Modifier.command("addtogroup", permission="#bot.admin.addtogroup")
    def cmd_addtogroup(self, context):
        group, username = context.args
        cfg = self.get_config()["users"].setdefault(username, {"permissions": [], "groups": []})
        if group not in cfg["groups"]:
            cfg["groups"].append(group)
        self.reset()
        self.save_config()

    @Modifier.command("removefromgroup", permission="#bot.admin.removefromgroup")
    def cmd_removefromgroup(self, context):
        group, username = context.args
        cfg = self.get_config()["users"].setdefault(username, {"permissions": [], "groups": []})
        if group in cfg["groups"]:
            cfg["groups"].remove(group)
        self.reset()
        self.save_config()

