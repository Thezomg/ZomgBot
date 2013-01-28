from ZomgBot.topo_sort import recursive_sort, free

import imp
import inspect
import os
from os import path
from glob import glob
from functools import wraps


class PluginManager(object):
    """
    Manage plugin loading and dependency resolution
    """
    plugins = {}
    instances = {}

    instance = None

    def __init__(self, parent):
        self.events = parent.events
        PluginManager.instance = self

    def load_plugins(self, package="ZomgBot.plugins"):
        modpath = path.join(os.curdir, *package.split('.') + ['*.py'])
        for mod in glob(modpath):
            if path.basename(mod).startswith("__init__."): continue
            m = imp.load_source(path.splitext(path.basename(mod))[0], mod)
        self.ordered_enable("BanManager")
        self.events.dispatchEvent(name="PluginsLoaded", event=None)
        print self.instances

    def enable(self, plugin):
        plugin = self.plugins[plugin]
        self.instances[plugin] = plugin(self)
        self.instances[plugin].setup()

    def disable(self, plugin):
        if isinstance(plugin, basestring):
            return self.disable(self.plugins[plugin])
        plugin.teardown()
        del self.plugins[plugin.name]

    def ordered_enable(self, *plugins):
        nodes = [(plugin.name, tuple(plugin.plugin_info["depends"] or [])) for plugin in self.plugins.values()]
        order = recursive_sort(nodes, set((plugin, d) for plugin, d in free(nodes) if plugin in plugins))
        print "Resolved plugin load order: {}".format(', '.join(order))
        for p in order:
            self.enable(p)


class Plugin(object):
    """
    Base class for all plugins
    """
    def __init__(self, parent):
        self.events = parent.events

    @staticmethod
    def register(depends=None, provides=None):
        def inner(cls):
            cls.name = cls.__module__.split(".")[-1]
            cls.plugin_info = {"depends": depends, "provides": provides}
            PluginManager.instance.plugins[cls.name] = cls

            # handle tags we may have left in decorators
            for m in dict(inspect.getmembers(cls, inspect.ismethod)).values():
                if not hasattr(m.__func__, "plugin"): continue  # we don't care
                m.__func__.plugin = cls

                if not hasattr(m.__func__, "event"): continue # not an event handler
                for event, priority in m.__func__.event:
                    def unfuck(m):  # we need a variable per iteration (i.e. m) in order to close over it
                        @wraps(m)
                        def wrapper(*a, **kw):
                            return m.__func__(PluginManager.instance.instances[cls], *a, **kw)
                        return wrapper
                    PluginManager.instance.events.addEventHandler(m.__func__.plugin, event, unfuck(m))
        return inner

    def setup(self):
        pass


class _Annotation(object):
    def __init__(self):
        self.all = {}

    def get(self, k):
        return self.all.get(k, [])
    
    def get_by_name(self, k):
        return dict((fn.__name__, fn) for fn in self.get(k))

    def __getattr__(self, k):
        def wrapper(*args, **kwargs):
            kwargs["args"] = args
            def inner(fn):
                @wraps(fn)
                def cc(*args, **kwargs):
                    return fn(PluginManager.instance.instances[fn.plugin], *args, **kwargs)
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