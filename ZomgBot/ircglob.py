﻿
import re

nick_user_host_re = r'^([^!@]+)!([^!@]+)@([^!@]+)$'


def matches(pattern, prefix):
    return glob(pattern).matches(prefix)


class glob(object):
    '''Represents a nick!user@host glob pattern'''

    def __init__(self, pattern):
        self.pattern = pattern

    @staticmethod
    def is_valid(nick_user_host):
        return glob.str_to_tuple(nick_user_host) != False

    def __eq__(self, other):
        return self.isequiv(other)

    def __repr__(self):
        return 'glob({})'.format(repr(self.pattern))

    @staticmethod
    def str_to_tuple(nick_user_host):
        '''Convert a "nick!user@host" to (nick, user, host)'''
        match = re.match(nick_user_host_re, nick_user_host, re.I)
        if not match:
            return False
        return match.groups()

    @staticmethod
    def pattern_to_re(pattern):
        '''Convert a glob pattern to a regex'''
        r = ''
        for bit in re.finditer(r'(?:[^\?\*]+|\?+|\*+)', pattern, re.I):
            if bit.group().startswith("*"):
                r += '[^!@]*'
            elif bit.group().startswith("?"):
                r += '[^!@]'
                if len(bit.group()) > 1:
                    r += '{%d}' % len(bit.group())
            else:
                r += re.escape(bit.group())
        return '^%s$' % r

    def matches(self, test):
        '''Return True if 'test' is matched by the pattern we represent'''
        return re.match(glob.pattern_to_re(self.pattern), test, re.I) != None

    @staticmethod
    def pattern_to_super_re(pattern):
        '''Like glob.pattern_to_re but for superset testing'''
        r = ''
        for bit in re.finditer(r'(?:[^\?\*]+|\?+|\*+)', pattern, re.I):
            if bit.group().startswith("*"):
                r += '[^!@]*'
            elif bit.group().startswith("?"):
                r += '[^!@*]'
                if len(bit.group()) > 1:
                    r += '{%d}' % len(bit.group())
            else:
                r += re.escape(bit.group())
        return '^%s$' % r

    def issuper(self, other):
        '''Return True if the set of all nick!user@host matched by this glob is a superset of those matched by 'other\''''
        return re.match(glob.pattern_to_super_re(self.pattern), other.pattern, re.I) != None

    def issub(self, other):
        '''Return True if the set of all nick!user@host matched by this glob is a subset of those matched by 'other\''''
        return other.issuper(self)

    def isequiv(self, other):
        '''Return True if this glob is exactly equivalent to 'other\''''
        return self.issuper(other) and self.issub(other)
