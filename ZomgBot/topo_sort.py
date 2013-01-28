def free(nodelist):
    """
    return all nodes n from nodelist which have no edges x->n
    (i.e. nothing depends on them)
    """
    dep = set()
    for k, v in nodelist:
        for n in v: dep.add(n)
    # dep is now a set of all nodes which -do- have edges x->n
    everything = set([k for k, v in nodelist])
    l = everything - dep
    return set((k, v) for k, v in nodelist if k in l)
 
 
def recursive_sort(nodelist, initial=None):
    """
    recursive (depth-first) topological sort of nodelist
    """
    sorted = []
    visited = set()
    if initial is None:
        initial = [free(nodelist)]
    def visit((n, d), stack=[]):
        if n in stack:
            # error condition
            l = stack[stack.index(n):] + [n]
            raise Exception('Cycle: ' + '->'.join(l))
        elif not n in visited:
            stack.append(n)
            depends = [(k, v) for k, v in nodelist if k in d]
            unmet = list(set(d) - set(k for k, v in depends))
            if unmet:
                raise Exception('Unmet dependencies: ' + ', '.join(unmet))
            for node in depends:
                visit(node, stack)
            stack[:] = stack[:-1]
            sorted.append(n)
            visited.add(n)
    for k, v in free:
        visit((k, v))
    if nodelist and not sorted:
        # just visit any node so we report a cycle
        visit(nodelist[0])
    return sorted
