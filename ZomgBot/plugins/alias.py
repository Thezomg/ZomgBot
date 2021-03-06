from ZomgBot.plugins import Plugin, Modifier
from ZomgBot.events import EventHandler, CancelEvent

from itertools import chain


class Alias(object):
    def __init__(self, match, replace):
        self.tokens = [s.lower() for s in match.split(" ")]
        if "$" in self.tokens:
            assert "$" not in self.tokens[:-1]
        self.replace = [r.lower() if r.startswith("$") else r for r in replace.split(" ")]
        for r in self.replace:
            if r.startswith("$"): assert r in self.tokens

    def match(self, str_):
        """
        Match `str_` against this Alias, returning a dict of $tokens and their replacements.
        """
        tokens = [s for s in str_.split(" ") if s]
        matches = {}
        for my_tok in self.tokens:
            assert tokens
            sr_tok = tokens.pop(0)
            if my_tok == "$":
                if "$" in matches:
                    matches["$"] += " " + sr_tok
                else:
                    matches["$"] = sr_tok
            elif my_tok.startswith("$"):
                if my_tok in matches:
                    assert sr_tok.lower() == matches[my_tok].lower()
                else:
                    matches[my_tok] = sr_tok
            else:
                assert sr_tok.lower() == my_tok.lower()
        assert len(tokens) == 0
        return matches
    
    def substitute_tokens(self, replacements):
        """
        Generator to spit out pieces of our replacement, substituting in the values from
        `replacements` (which should be the return value of a call to match())
        """
        for tok in self.replace:
            if tok.startswith("$"):
                assert tok in replacements
                yield replacements[tok]
            else:
                yield tok
    
    def apply(self, str_):
        """
        Applies this alias to an input string `str_`.
        """
        replacements = self.match(str_)
        return " ".join(self.substitute_tokens(replacements))
    
    def check(self, str_):
        """
        Identical to apply() but returns False if the match fails (instead of raising an
        exception)
        """
        try:
            return self.apply(str_)
        except AssertionError:
            return False

    @property
    def thing(self):
        return {"match": str(" ".join(self.tokens)), "replace": str(" ".join(self.replace))}


@Plugin.register(depends=["commands"])
class AliasPlugin(Plugin):
    def setup(self):
        self.commands = self.parent.get_plugin("commands")
        cfg = self.get_config().get("aliases", [])
        self.aliases = {}
        for thing in cfg:
            try:
                alias = Alias(thing["match"], thing["replace"])
                name = alias.tokens[0]
                self.aliases.setdefault(name, []).append(alias)
            except: pass

    def save(self):
        cfg = [a.thing for a in chain(*self.aliases.values())]
        self.get_config()["aliases"] = cfg
        self.save_config()

    def find_alias(self, str_):
        toks = [s.lower() for s in str_.split(" ")]
        if toks[0] not in self.aliases: return False
        for alias in self.aliases[toks[0]]:
            if alias.tokens == toks:
                return alias
        return False

    @Modifier.command("alias", permission="#alias.alias")
    def cmd_alias(self, context):
        if "=" in context.full:
            match, replace = [s.strip() for s in context.full.split("=", 1)]
        else:
            match, replace = context.full.strip(), None
        m = self.find_alias(match)
        if m:
            self.aliases[m.tokens[0]].remove(m)
        if replace:
            alias = Alias(match, replace)
            self.aliases.setdefault(alias.tokens[0], []).append(alias)
        self.save()

    @EventHandler("CommandPreprocess")
    def on_CommandPreprocess(self, event):
        commandname = event.command.split(" ", 1)[0]
        if commandname not in self.aliases: return
        for alias in self.aliases[commandname]:
            r = alias.check(event.command)
            if r:
                print "*** alias: transforming [{}] -> [{}]".format(event.command, r)
                self.commands.dispatch_command(event.user, r, event.channel)
                raise CancelEvent
