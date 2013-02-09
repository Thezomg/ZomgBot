from ZomgBot.plugins import Plugin, Modifier, PluginManager
from twisted.internet import task
from ZomgBot.events import Event, EventHandler

from functools import partial

@Plugin.register(depends=["auth", "permission"])
class Commands(Plugin):
    autostart = []

    @EventHandler("PluginsLoaded")
    def handle_reload(self, event):
        self.tasks = {}
        tasks = Modifier.get("repeat")
        for t in tasks:
            a = t.annotation["repeat"]
            if self.tasks.has_key(a["args"][0]):
                print "Already a task with the name {}, error loading second one from plugin {}".format(a["args"][0], t.plugin.name)
                continue

            l = task.LoopingCall(t, PluginManager.instance.instances[t.plugin])
            if a.get("autostart", False):
                if self.bot.irc is None:
                    self.autostart.append(partial(l.start, a.get("time", 1.0)))
                else:
                    l.start(a.get("time", 1.0))
            self.tasks[a["args"][0]] = l

    def teardown(self):
        for k, t in self.tasks.items():
            if t.running:
                t.stop()
        t = {}

    def _stop_task(self, taskname):
        if self.tasks.has_key(taskname):
            t = self.tasks[taskname]
            if t.running:
                t.stop()
                return True
        return False

    def _start_task(self, taskname):
        if self.tasks.has_key(taskname):
            t = self.tasks[taskname]
            if not t.running:
                a = t.f.annotation["repeat"]
                print t.f.annotation
                t.start(a.get("time", 1.0))
                return True
        return False

    @EventHandler("SignedOn")
    def on_SignedOn(self, event):
        for task in self.autostart:
            task()
        self.autostart = []

    @Modifier.command("stoptask")
    def stop_task(self, context):
        if context.args:
            if self._stop_task(context.args[0]):
                context.reply("Task stopped")
            else:
                context.reply("Task not running or doesn't exist")
        else:
            context.reply("Provide a task name to stop")

    @Modifier.command("starttask")
    def start_task(self, context):
        if context.args:
            if self._start_task(context.args[0]):
                context.reply("Task started")
            else:
                context.reply("Task already running or doesn't exist")
        else:
            context.reply("Provide a task name to start")

    @Modifier.repeat("repeating", time=5.0, autostart=False)
    def repeat_command(self):
        self.send_message('#llama5', "testing loop (5 seconds)")