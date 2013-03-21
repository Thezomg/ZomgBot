from ZomgBot.topo_sort import recursive_sort, free

import imp
import inspect
import os
from os import path
from glob import glob
from functools import wraps

from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import scoped_session


class PluginManager(object):
    """
    Manage plugin loading and dependency resolution
    """
    plugins = {}
    instances = {}

    d_bases = {}

    instance = None

    def __init__(self, parent):
        self.parent = parent
        self.events = parent.events
        PluginManager.instance = self

    def load_plugins(self, package="ZomgBot.plugins"):
        modpath = path.join(os.curdir, *package.split('.') + ['*.py'])
        for mod in glob(modpath):
            if path.basename(mod).startswith("__init__."): continue
            try:
                m = imp.load_source(path.splitext(path.basename(mod))[0], mod)
            except Exception as e:
                print "Encountered {} loading {}".format(e, mod)
        self.ordered_enable(*self.parent.config["bot"]["plugins"])
        self.events.dispatchEvent(name="PluginsLoaded", event=None)
        print self.instances

    def get_plugin(self, plugin_name):
        if self.plugins.has_key(plugin_name):
            if self.instances.has_key(self.plugins[plugin_name]):
                return self.instances[self.plugins[plugin_name]]
        return None

    def enable(self, plugin):
        plugin = self.plugins[plugin]
        self.instances[plugin] = plugin(self)

    def disableAll(self):
        for p in self.instances.values():
            self.disable(p)
        self.instances = {}

    def disable(self, plugin):
        if isinstance(plugin, basestring):
            return self.disable(self.plugins[plugin])
        print plugin
        plugin.teardown()
        self.events.unregisterHandlers(plugin.__class__)
        del self.plugins[plugin.name]
        if plugin.name in self.d_bases: del self.d_bases[plugin.name]

    def ordered_enable(self, *plugins):
        nodes = [(plugin.name, tuple(plugin.plugin_info["depends"] or [])) for plugin in self.plugins.values()]
        order = recursive_sort(nodes, set((plugin, d) for plugin, d in free(nodes) if self.plugins[plugin].name in plugins))
        print "{}: Resolved plugin load order: {}".format(plugins, ', '.join(order))
        for p in order:
            self.enable(p)

    def install_databases(self, plugin):
        assert plugin in self.d_bases
        self.d_bases[plugin].metadata.create_all(self.parent.db_engine)


class Plugin(object):
    """
    Base class for all plugins
    """
    def __init__(self, parent):
        self.events = parent.events
        self.parent = parent
        self.bot = parent.parent

        if self.plugin_info.get("db", False):
            self._session = scoped_session(self.bot.sessionmaker)
            parent.install_databases(self.name)
        else:
            self._session = False

        for m in dict(inspect.getmembers(self, inspect.ismethod)).values():
            if not hasattr(m.__func__, "event"): continue # not an event handler
            for event, priority in m.__func__.event:
                PluginManager.instance.events.addEventHandler(m.__func__.plugin, event, m, priority=priority)

        self.setup()

    @property
    def db(self):
        if not self._session: return None
        return self._session()

    @staticmethod
    def register(depends=None, uses_db=False, name=None):
        def inner(cls):
            cls.name = name or cls.__module__.split(".")[-1]
            cls.plugin_info = {"depends": depends, "db": uses_db}
            PluginManager.instance.plugins[cls.name] = cls

            # handle tags we may have left in decorators
            for m in dict(inspect.getmembers(cls, inspect.ismethod)).values():
                if not hasattr(m.__func__, "plugin"): continue  # we don't care
                m.__func__.plugin = cls
                
        return inner

    @staticmethod
    def declarative_base(plugin):
        if plugin in PluginManager.instance.d_bases:
            return PluginManager.instance.d_bases[plugin]

        class base(object):
            @declared_attr
            def __tablename__(cls):
                return '_{}_{}'.format(plugin.lower(), cls.__name__.lower())

        base = declarative_base(cls=base)
        PluginManager.instance.d_bases[plugin] = base
        return base

    def setup(self):
        pass

    def teardown(self):
        pass

    def send_message(self, target, message):
        if self.parent.parent.irc:
            self.parent.parent.irc.send_message(target, message)

    def get_config(self, name=None):
        cfg = self.parent.parent.config
        cfg.setdefault("plugins", {})
        return cfg["plugins"].setdefault(name or self.name, {})

    def save_config(self):
        self.parent.parent.config.threaded_save()


class _Annotation(object):
    def __init__(self):
        self.all = {}

    def get(self, k):
        return [fn for fn in self.all.get(k, []) if fn.plugin in PluginManager.instance.instances]
    
    def get_by_name(self, k):
        return dict((fn.__name__, fn) for fn in self.get(k))

    def forgetPlugin(self, plugin):
        self.all = dict((k, [f for f in v if f.plugin != plugin]) for k, v in self.all)

    def forgetEverything(self):
        self.all = {}

    def __getattr__(self, k):
        def wrapper(*args, **kwargs):
            kwargs["args"] = args
            def inner(fn):
                @wraps(fn)
                def cc(*args, **kwargs):
                    return fn.__get__(PluginManager.instance.instances[fn.plugin], fn.plugin)(*args, **kwargs)
                self.all.setdefault(k, [])
                self.all[k].append(fn)
                fn.annotation = getattr(fn, "annotation", {})
                fn.annotation[k] = kwargs
                fn.plugin = None
                fn.call_with_self = cc
                return fn
            return inner
        return wrapper


Modifier = _Annotation()
