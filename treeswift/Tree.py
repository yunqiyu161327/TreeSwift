#! /usr/bin/env python
from treeswift.Node import Node
from copy import copy
from gzip import open as gopen
from os.path import isfile
from warnings import warn
try:                # Python 3
    from queue import Queue,PriorityQueue
except ImportError: # Python 2
    from Queue import Queue,PriorityQueue
INVALID_NEWICK = "Tree not valid Newick tree"
INVALID_NEXML = "Invalid valid NeXML File"

class Tree:
    '''Tree class'''
    def __init__(self):
        '''Tree constructor'''
        self.root = Node()  # root Node object

    def __str__(self):
        '''Represent this Tree as a string

        Returns:
            str: string representation of this Tree (Newick string)
        '''
        return self.newick()

    def __copy__(self):
        '''Copy this Tree

        Returns:
            Tree: A copy of this tree
        '''
        return self.extract_tree(None, False, False)


    def avg_branch_length(self, terminal=True, internal=True):
        '''Compute the average length of the selected branches of this Tree. Edges with length None will be treated as 0-length

        Args:
            terminal (bool): True to include terminal branches, otherwise False

            internal (bool): True to include internal branches, otherwise False

        Returns:
            The average length of the selected branches
        '''
        if not internal and not terminal:
            raise RuntimeError("Must select either internal or terminal branches (or both)")
        tot = 0.; num = 0
        for node in self.traverse_preorder():
            if node.edge_length is not None and (internal and not node.is_leaf()) or (terminal and node.is_leaf()):
                tot += node.edge_length; num += 1
        return tot/num

    def branch_lengths(self, terminal=True, internal=True):
        '''Generator over the lengths of the selected branches of this Tree. Edges with length None will be output as 0-length

        Args:
            terminal (bool): True to include terminal branches, otherwise False

            internal (bool): True to include internal branches, otherwise False
        '''
        for node in self.traverse_preorder():
            if (internal and not node.is_leaf()) or (terminal and node.is_leaf()):
                if node.edge_length is None:
                    yield 0
                else:
                    yield node.edge_length

    def closest_leaf_to_root(self):
        '''Return the leaf that is closest to the root and the corresponding distance. Edges with no length will be considered to have a length of 0

        Returns:
            tuple: First value is the closest leaf to the root, and second value is the corresponding distance
        '''
        best = (None,float('inf')); d = dict()
        for node in self.traverse_preorder():
            d[node] = {True:0,False:node.edge_length}[node.edge_length is None]
            if not node.is_root():
                d[node] += d[node.parent]
            if node.is_leaf() and d[node] < best[1]:
                best = (node,d[node])
        return best

    def coalescence_times(self, backward=True):
        '''Generator over the times of successive coalescence events

        Args:
            backward (bool): True to go backward in time (i.e., leaves to root), otherwise False
        '''
        pq = PriorityQueue()
        if backward:
            mult = -1
        else:
            mult = 1
        for n,d in self.distances_from_root():
            if len(n.children) > 1:
                pq.put(mult*d)
        while not pq.empty():
            yield mult*pq.get()

    def coalescence_waiting_times(self, backward=True):
        '''Generator over the waiting times of successive coalescence events

        Args:
            backward (bool): True to go backward in time (i.e., leaves to root), otherwise False
        '''
        pq = PriorityQueue(); lowest_leaf_dist = float('-inf')
        if backward:
            mult = -1
        else:
            mult = 1
        for n,d in self.distances_from_root():
            if len(n.children) > 1:
                pq.put(mult*d)
            elif len(n.children) == 0 and d > lowest_leaf_dist:
                lowest_leaf_dist = d
        pq.put(mult*lowest_leaf_dist); curr = mult*pq.get()
        while not pq.empty():
            next = mult*pq.get(); yield abs(curr-next); curr = next

    def collapse_short_branches(self, threshold):
        '''Collapse internal branches (not terminal branches) with length less than or equal to `threshold`. A branch length of `None` is considered 0

        Args:
            threshold (float): The threshold to use when collapsing branches
        '''
        if not isinstance(threshold,float) and not isinstance(threshold,int):
            raise RuntimeError("threshold must be an integer or a float")
        elif threshold < 0:
            raise RuntimeError("threshold cannot be negative")
        q = Queue(); q.put(self.root)
        while not q.empty():
            next = q.get()
            if next.edge_length is None or next.edge_length <= threshold:
                if next.is_root():
                    next.edge_length = None
                elif not next.is_leaf():
                    parent = next.parent; parent.remove_child(next)
                    for c in next.children:
                        parent.add_child(c)
            for c in next.children:
                q.put(c)

    def diameter(self):
        '''Compute the diameter (maximum leaf pairwise distance) of this Tree

        Returns:
            float: The diameter of this Tree
        '''
        d = dict(); best = float('-inf')
        for node in self.traverse_postorder():
            if node.is_leaf():
                d[node] = 0
            else:
                dists = sorted(d[c]+c.edge_length for c in node.children)
                d[node] = dists[-1]; max_pair = dists[-1]+dists[-2]
                if max_pair > best:
                    best = max_pair
        return best

    def distance_matrix(self):
        '''Return a distance matrix (2D dictionary) of the leaves of this Tree

        Returns:
            dict: Distance matrix (2D dictionary) of the leaves of this Tree, where keys are Node objects; M[u][v] = distance from u to v
        '''
        M = dict(); leaf_dists = dict()
        for node in self.traverse_postorder():
            if node.is_leaf():
                leaf_dists[node] = [[node,0]]
            else:
                for c in node.children:
                    if c.edge_length is not None:
                        for i in range(len(leaf_dists[c])):
                            leaf_dists[c][i][1] += c.edge_length
                for c1 in range(0,len(node.children)-1):
                    leaves_c1 = leaf_dists[node.children[c1]]
                    for c2 in range(c1+1,len(node.children)):
                        leaves_c2 = leaf_dists[node.children[c2]]
                        for i in range(len(leaves_c1)):
                            for j in range(len(leaves_c2)):
                                u,ud = leaves_c1[i]; v,vd = leaves_c2[j]; d = ud+vd
                                if u not in M:
                                    M[u] = dict()
                                M[u][v] = d
                                if v not in M:
                                    M[v] = dict()
                                M[v][u] = d
                leaf_dists[node] = leaf_dists[node.children[0]]; del leaf_dists[node.children[0]]
                for i in range(1,len(node.children)):
                    leaf_dists[node] += leaf_dists[node.children[i]]; del leaf_dists[node.children[i]]
        return M

    def distances_from_root(self, leaves=True, internal=True):
        '''Generator over the root-to-node distances of this Tree; (node,distance) tuples'''
        if leaves or internal:
            d = dict()
            for node in self.traverse_preorder():
                if node.is_root():
                    d[node] = 0
                else:
                    d[node] = d[node.parent]
                if node.edge_length is not None:
                    d[node] += node.edge_length
                if (node.is_leaf() and leaves) or (not node.is_leaf() and internal):
                    yield (node,d[node])

    def edge_length_sum(self, terminal=True, internal=True):
        '''Compute the sum of all selected edge lengths in this Tree

        Args:
            terminal (bool): `True` to include terminal branches, otherwise `False`

            internal (bool): `True` to include internal branches, otherwise `False`

        Returns:
            float: Sum of all selected edge lengths in this Tree
        '''
        return sum(node.edge_length for node in self.traverse_preorder() if node.edge_length is not None and ((terminal and node.is_leaf()) or (internal and not node.is_leaf())))

    def extract_tree(self, labels, without, suppress_unifurcations=True):
        '''Helper function for extract_tree_* functions'''
        if labels is not None and not isinstance(labels, set):
            labels = set(labels)
        label_to_leaf = dict(); keep = set()
        for node in self.traverse_leaves():
            label_to_leaf[str(node)] = node
            if labels is None or (without and str(node) not in labels) or (not without and str(node) in labels):
                keep.add(node)
        for node in list(keep):
            for a in node.traverse_ancestors(include_self=False):
                keep.add(a)
        out = Tree(); out.root.label = self.root.label; out.root.edge_length = self.root.edge_length
        q_old = Queue(); q_old.put(self.root)
        q_new = Queue(); q_new.put(out.root)
        while not q_old.empty():
            n_old = q_old.get(); n_new = q_new.get()
            for c_old in n_old.children:
                if c_old in keep:
                    c_new = Node(label=str(c_old), edge_length=c_old.edge_length); n_new.add_child(c_new)
                    q_old.put(c_old); q_new.put(c_new)
        if suppress_unifurcations:
            out.suppress_unifurcations()
        return out

    def extract_tree_without(self, labels, suppress_unifurcations=True):
        '''Extract a copy of this Tree without the leaves labeled by the strings in `labels`

        Args:
            labels (set): Set of leaf labels to exclude

            suppress_unifurcations (bool): True to suppress unifurcations, otherwise False

        Returns:
            Tree: Copy of this Tree, exluding the leaves labeled by the strings in `labels`
        '''
        return self.extract_tree(labels, True, suppress_unifurcations)

    def extract_tree_with(self, labels, suppress_unifurcations=True):
        '''Extract a copy of this Tree with only the leaves labeled by the strings in `labels`

        Args:
            leaves (set): Set of leaf labels to include.

            suppress_unifurcations (bool): True to suppress unifurcations, otherwise False

        Returns:
            Tree: Copy of this Tree, including only the leaves labeled by the strings in `labels`
        '''
        return self.extract_tree(labels, False, suppress_unifurcations)

    def furthest_from_root(self):
        '''Return the Node that is furthest from the root and the corresponding distance. Edges with no length will be considered to have a length of 0

        Returns:
            tuple: First value is the furthest Node from the root, and second value is the corresponding distance
        '''
        best = (self.root,0); d = dict()
        for node in self.traverse_preorder():
            d[node] = {True:0,False:node.edge_length}[node.edge_length is None]
            if not node.is_root():
                d[node] += d[node.parent]
            if d[node] > best[1]:
                best = (node,d[node])
        return best

    def gamma_statistic(self):
        '''Compute the Gamma statistic of Pybus and Harvey (2000)

        Returns:
            float: The Gamma statistic of Pybus and Harvey (2000)
        '''
        t = copy(self); t.resolve_polytomies() # need fully bifurcating tree
        G = [g for g in t.coalescence_times(backward=False)]
        n = len(G)+1
        if n <= 2:
            raise RuntimeError("Gamma statistic can only be computed on trees with more than 2 leaves")
        T = sum((j+2)*g for j,g in enumerate(G))
        out = 0.
        for i in range(len(G)-1):
            for k in range(i+1):
                out += (k+2)*G[k]
        out /= (n-2)
        out -= (T/2)
        out /= T
        out /= (1./(12*(n-2)))**0.5
        return out

    def height(self):
        '''Compute the height (i.e., maximum distance from root) of this tree

        Returns:
            float: The height (i.e., maximum distance from root) of this tree
        '''
        return max(d[1] for d in self.distances_from_root())

    def label_to_node(self, selection='leaves'):
        '''Return a dictionary mapping labels (strings) to Node objects. If `selection` is `"all"`, the dictionary will contain all nodes. If `selection` is `"leaves"`, the dictionary will only contain leaves. If `selection` is `"internal"`, the dictionary will only contain internal nodes. If `selection` is a `set`, the dictionary will contain all nodes labeled by a label in `selection`. If multiple nodes are labeled by a given label, only the last (preorder traversal) will be obtained

        Args:
            selection (str or set): `"all"` to select all nodes, `"leaves"` to select leaves, `"internal"` to select internal nodes, or a `set` of labels to specify nodes to select

        Returns:
            dict: Dictionary mapping labels to the corresponding nodes
        '''
        if not isinstance(selection,set) and not isinstance(selection,list) and (not isinstance(selection,str) or not (selection != 'all' or selection != 'leaves' or selection != 'internal')):
            raise RuntimeError('"selection" must be one of the strings "all", "leaves", or "internal", or it must be a set containing Node labels')
        if isinstance(selection, str):
            selection = selection[0]
        elif isinstance(selection,list):
            selection = set(selection)
        label_to_node = dict()
        for node in self.traverse_preorder():
            if selection == 'a' or (selection == 'i' and not node.is_leaf()) or (selection == 'l' and node.is_leaf()) or str(node) in selection:
                label_to_node[str(node)] = node
        if not isinstance(selection,str) and len(label_to_node) != len(selection):
            warn("Not all given labels exist in the tree")
        return label_to_node

    def mrca(self, labels):
        '''Return the Node that is the MRCA of the nodes labeled by a label in `labels`. If multiple nodes are labeled by a given label, only the last (preorder traversal) will be obtained

        Args:
            labels (set): Set of leaf labels

        Returns:
            Node: The MRCA of the Node objects labeled by a label in `labels`
        '''
        l2n = self.label_to_node(labels)
        count = dict()
        for node in l2n.values():
            for a in node.traverse_ancestors():
                if a not in count:
                    count[a] = 0
                count[a] += 1
                if count[a] == len(l2n):
                    return a
        raise RuntimeError("There somehow does not exist an MRCA for the given labels")

    def mrca_matrix(self):
        '''Return a dictionary storing all pairwise MRCAs. M[u][v] = MRCA of nodes u and v. Excludes M[u][u] because MRCA of node and itself is itself.

        Returns:
            dict: M[u][v] = MRCA of nodes u and v
        '''
        M = dict()
        leaves_below = dict()
        for node in self.traverse_postorder():
            leaves_below[node] = list()
            if node.is_leaf():
                leaves_below[node].append(node); M[node] = dict()
            else:
                for i in range(len(node.children)-1):
                    for l1 in leaves_below[node.children[i]]:
                        leaves_below[node].append(l1)
                        for j in range(i+1, len(node.children)):
                            for l2 in leaves_below[node.children[j]]:
                                M[l1][l2] = node; M[l2][l1] = node
                if len(node.children) != 1:
                    for l2 in leaves_below[node.children[-1]]:
                        leaves_below[node].append(l2)
        return M

    def newick(self):
        '''Output this Tree as a Newick string

        Returns:
            str: Newick string of this Tree
        '''
        if self.root.edge_length is None:
            return '%s;' % self.root.newick()
        else:
            return '%s:%f;' % (self.root.newick(), self.root.edge_length)

    def num_lineages_at(self, distance):
        '''Returns the number of lineages of this Tree that exist `distance` away from the root

        Args:
            distance (float): The distance away from the root

        Returns:
            int: The number of lineages that exist `distance` away from the root
        '''
        if distance < 0:
            raise RuntimeError("distance cannot be negative")
        d = dict(); q = Queue(); q.put(self.root); count = 0
        while not q.empty():
            node = q.get()
            if node.is_root():
                d[node] = 0
            else:
                d[node] = d[node.parent]
            if node.edge_length is not None:
                d[node] += node.edge_length
            if d[node] < distance:
                for c in node.children:
                    q.put(c)
            elif node.parent is None or d[node.parent] < distance:
                count += 1
        return count

    def num_nodes(self, leaves=True, internal=True):
        '''Compute the total number of selected nodes in this Tree

        Args:
            leaves (bool): True to include leaves, otherwise False

            internal (bool): True to include internal nodes, otherwise False

        Returns:
            int: The total number of selected nodes in this Tree
        '''
        num = 0
        for node in self.traverse_preorder():
            if (leaves and node.is_leaf()) or (internal and not node.is_leaf()):
                num += 1
        return num

    def reroot(self, node, length, suppress_unifurcations=True):
        '''Reroot this Tree at `length` up the incident edge of `node`

        Args:
            node (Node): The node on whose incident edge this `Tree` will be rerooted

            length (float): The distance up the specified edge at which to reroot this `Tree`

            suppress_unifurcations (bool): True to suppress unifurcations, otherwise False
        '''
        if self.root.edge_length is not None:
            raise ValueError("Attempting to reroot a tree with a root edge")
        if (node.edge_length is None or node.edge_length == 0) and length != 0:
            raise ValueError("Attempting to reroot at non-zero length on 0-length edge")
        if length < 0:
            raise ValueError("Specified length at which to reroot must be positive")
        if length > node.edge_length:
            raise ValueError("Specified length must be shorter than the edge at which to reroot")
        ancestors = [a for a in node.traverse_ancestors(include_self=False)]
        for i in range(len(ancestors)-2,-1,-1):
            child = ancestors[i]; parent = ancestors[i+1]
            parent.remove_child(child)
            child.add_child(parent)
            parent.edge_length = child.edge_length
        sibling = node.parent; sibling.children.remove(node)
        self.root = Node(); self.root.children = [node,sibling]
        sibling.edge_length = node.edge_length - length; node.edge_length = length
        if suppress_unifurcations:
            self.suppress_unifurcations()

    def resolve_polytomies(self):
        '''Arbitrarily resolve polytomies with 0-lengthed edges.'''
        q = Queue(); q.put(self.root)
        while not q.empty():
            node = q.get()
            while len(node.children) > 2:
                c1 = node.children.pop(); c2 = node.children.pop()
                nn = Node(edge_length=0); node.add_child(nn)
                nn.add_child(c1); nn.add_child(c2)
            for c in node.children:
                q.put(c)

    def sackin(self, normalize='leaves'):
        '''Compute the Sackin index of this Tree

        Args:
            normalize (str): None to not normalize, "leaves" to normalize by the number of leaves, "yule" to normalize to the Yule model, or "pda" to normalize to the Proportional to Distinguishable
            Arrangements model

        Returns:
            float: Sackin index (either normalized or not)
        '''
        num_nodes_from_root = dict(); sackin = 0; num_leaves = 0
        for node in self.traverse_preorder():
            num_nodes_from_root[node] = 1
            if not node.is_root():
                num_nodes_from_root[node] += num_nodes_from_root[node.parent]
            if node.is_leaf():
                num_nodes_from_root[node] -= 1; sackin += num_nodes_from_root[node]; num_leaves += 1
        if normalize is None or normalize is False:
            return sackin
        elif normalize == 'leaves':
            return float(sackin)/num_leaves
        elif normalize == 'yule':
            x = sum(1./i for i in range(2, num_leaves+1))
            return (sackin - (2*num_leaves*x)) / num_leaves
        elif normalize == 'pda':
            return sackin/(num_leaves**1.5)
        else:
            raise RuntimeError("normalize must be None, 'leaves', 'yule', or 'pda'")

    def scale_edges(self, multiplier):
        '''Multiply all edges in this Tree by `multiplier`'''
        if not isinstance(multiplier,int) and not isinstance(multiplier,float):
            raise RuntimeError("multiplier must be an int or float")
        for node in self.traverse_preorder():
            if node.edge_length is not None:
                node.edge_length *= multiplier

    def suppress_unifurcations(self):
        '''Remove all nodes with only one child and directly attach child to parent'''
        q = Queue(); q.put(self.root)
        while not q.empty():
            node = q.get()
            if len(node.children) != 1:
                for c in node.children:
                    q.put(c)
                continue
            child = node.children.pop()
            if node.is_root():
                self.root = child; child.parent = None
            else:
                parent = node.parent; parent.remove_child(node); parent.add_child(child)
            if node.edge_length is not None:
                if child.edge_length is None:
                    child.edge_length = 0
                child.edge_length += node.edge_length
            q.put(child)

    def traverse_inorder(self):
        '''Perform an inorder traversal of the Node objects in this Tree'''
        for node in self.root.traverse_inorder():
            yield node

    def traverse_internal(self):
        '''Traverse over the internal nodes of this Tree'''
        for node in self.root.traverse_internal():
            yield node

    def traverse_leaves(self):
        '''Traverse over the leaves of this Tree'''
        for node in self.root.traverse_leaves():
            yield node

    def traverse_levelorder(self):
        '''Perform a levelorder traversal of the Node objects in this Tree'''
        for node in self.root.traverse_levelorder():
            yield node

    def traverse_postorder(self):
        '''Perform a postorder traversal of the Node objects in this Tree'''
        for node in self.root.traverse_postorder():
            yield node

    def traverse_preorder(self):
        '''Perform a preorder traversal of the Node objects in this Tree'''
        for node in self.root.traverse_preorder():
            yield node

    def traverse_rootdistorder(self, ascending=True):
        '''Perform a traversal of the Node objects in this Tree in either ascending (`ascending=True`) or descending (`ascending=False`) order of distance from the root'''
        pq = PriorityQueue(); dist_from_root = dict()
        for node in self.traverse_preorder():
            if node.is_root():
                d = 0
            else:
                d = dist_from_root[node.parent] + node.edge_length
            dist_from_root[node] = d
            if ascending:
                pq.put((d,node))
            else:
                pq.put((-d,node))
        while not pq.empty():
            priority,node = pq.get()
            if ascending:
                yield (priority,node)
            else:
                yield (-priority,node)

    def treeness(self):
        '''Compute the "treeness" (sum of internal branch lengths / sum of all branch lengths) of this Tree. Branch lengths of None are considered 0 length

        Returns:
            float: "Treeness" of this Tree (sum of internal branch lengths / sum of all branch lengths)
        '''
        internal = 0.; all = 0.
        for node in self.traverse_preorder():
            if node.edge_length is not None:
                all += node.edge_length
                if not node.is_leaf():
                    internal += node.edge_length
        return internal/all

    def write_tree_newick(self, filename):
        '''Write this Tree to a Newick file

        Args:
            filename (str): Path to desired output file (plain-text or gzipped)
        '''
        if filename.lower().endswith('.gz'): # gzipped file
            f = gopen(filename,'wb',9); f.write(self.newick().encode()); f.close()
        else: # plain-text file
            f = open(filename,'w'); f.write(self.newick()); f.close()

def read_tree_newick(newick):
    '''Read a tree from a Newick string or file

    Args:
        newick (str): Either a Newick string or the path to a Newick file (plain-text or gzipped)

    Returns:
        Tree: The tree represented by `newick`. If the Newick file has multiple trees (one per line), a list of `Tree` objects will be returned
    '''
    if newick.lower().endswith('.gz'): # gzipped file
        ts = gopen(newick).read().decode().strip()
        lines = ts.splitlines()
        if len(lines) != 1:
            return [read_tree_newick(l) for l in lines]
    elif isfile(newick): # plain-text file
        ts = open(newick).read().strip()
        lines = ts.splitlines()
        if len(lines) != 1:
            return [read_tree_newick(l) for l in lines]
    else:
        ts = newick.strip()
        lines = ts.splitlines()
        if len(lines) != 1:
            return [read_tree_newick(l) for l in lines]
    if ts[0] == '[':
        ts = ']'.join(ts.split(']')[1:]).strip()
    t = Tree(); n = t.root; i = 0
    while i < len(ts):
        if ts[i] == ';':
            if i != len(ts)-1 or n != t.root:
                raise RuntimeError(INVALID_NEWICK)
        elif ts[i] == '(':
            c = Node(); n.add_child(c); n = c
        elif ts[i] == ')':
            n = n.parent
        elif ts[i] == ',':
            n = n.parent; c = Node(); n.add_child(c); n = c
        elif ts[i] == ':':
            i += 1; ls = ''
            while ts[i] != ',' and ts[i] != ')' and ts[i] != ';':
                ls += ts[i]; i += 1
            n.edge_length = float(ls); i -= 1
        else:
            label = ''
            while ts[i] != ':' and ts[i] != ',' and ts[i] != ';' and ts[i] != ')':
                label += ts[i]; i += 1
            i -= 1; n.label = label
        i += 1
    return t

def read_tree_nexml(nexml):
    '''Read a tree from a NeXML string or file

    Args:
        nexml (str): Either a NeXML string or the path to a NeXML file (plain-text or gzipped)

    Returns:
        dict of Tree: A dictionary of the trees represented by `nexml`, where keys are tree names (`str`) and values are `Tree` objects
    '''
    if nexml.lower().endswith('.gz'): # gzipped file
        f = gopen(nexml)
    elif isfile(nexml): # plain-text file
        f = open(nexml)
    else:
        f = nexml.splitlines()
    trees = dict(); id_to_node = dict(); tree_id = None
    for line in f:
        if isinstance(line,bytes):
            l = line.decode().strip()
        else:
            l = line.strip()
        l_lower = l.lower()
        # start of tree
        if l_lower.startswith('<tree '):
            if tree_id is not None:
                raise ValueError(INVALID_NEXML)
            parts = l.split()
            for part in parts:
                if '=' in part:
                    k,v = part.split('='); k = k.strip()
                    if k.lower() == 'id':
                        tree_id = v.split('"')[1]; break
            if tree_id is None:
                raise ValueError(INVALID_NEXML)
            trees[tree_id] = Tree(); trees[tree_id].root = None
        # end of tree
        elif l_lower.replace(' ','').startswith('</tree>'):
            if tree_id is None:
                raise ValueError(INVALID_NEXML)
            id_to_node = dict(); tree_id = None
        # node
        elif l_lower.startswith('<node '):
            if tree_id is None:
                raise ValueError(INVALID_NEXML)
            node_id = None; node_label = None; is_root = False
            k = ''; v = ''; in_key = True; in_quote = False
            for i in range(6, len(l)):
                if l[i] == '"' or l[i] == "'":
                    in_quote = not in_quote
                if not in_quote and in_key and l[i] == '=':
                    in_key = False
                elif not in_quote and not in_key and (l[i] == '"' or l[i] == "'"):
                    k = k.strip()
                    if k.lower() == 'id':
                        node_id = v
                    elif k.lower() == 'label':
                        node_label = v
                    elif k.lower() == 'root' and v.strip().lower() == 'true':
                        is_root = True
                    in_key = True; k = ''; v = ''
                elif in_key and not (l[i] == '"' or l[i] == "'"):
                    k += l[i]
                elif not in_key and not (l[i] == '"' or l[i] == "'"):
                    v += l[i]
            if node_id is None or node_id in id_to_node:
                raise ValueError(INVALID_NEXML)
            id_to_node[node_id] = Node(label=node_label)
            if is_root:
                if trees[tree_id].root is not None:
                    raise ValueError(INVALID_NEXML)
                trees[tree_id].root = id_to_node[node_id]
        # edge
        elif l_lower.startswith('<edge '):
            if tree_id is None:
                raise ValueError(INVALID_NEXML)
            source = None; target = None; length = None
            parts = l.split()
            for part in parts:
                if '=' in part:
                    k,v = part.split('='); k = k.strip(); k_lower = k.lower()
                    if k_lower == 'source':
                        source = v.split('"')[1]
                    elif k_lower == 'target':
                        target = v.split('"')[1]
                    elif k_lower == 'length':
                        length = float(v.split('"')[1])
            if source is None or target is None or length is None:
                raise ValueError(INVALID_NEXML)
            if source not in id_to_node:
                raise ValueError(INVALID_NEXML)
            if target not in id_to_node:
                raise ValueError(INVALID_NEXML)
            id_to_node[source].add_child(id_to_node[target])
            id_to_node[target].edge_length = length
        elif l_lower.startswith('<rootedge '):
            if tree_id is None:
                raise ValueError(INVALID_NEXML)
            root_node = None; length = None
            parts = l.split()
            for part in parts:
                if '=' in part:
                    k,v = part.split('='); k = k.strip(); k_lower = k.lower()
                    if k_lower == 'target':
                        root_node = id_to_node[v.split('"')[1]]
                    elif k_lower == 'length':
                        length = float(v.split('"')[1])
            if trees[tree_id].root is None:
                raise ValueError(INVALID_NEXML)
            if root_node is not None and trees[tree_id].root != root_node:
                raise ValueError(INVALID_NEXML)
            trees[tree_id].root.edge_length = length
    return trees

def read_tree_nexus(nexus):
    '''Read a tree from a Nexus string or file

    Args:
        nexus (str): Either a Nexus string or the path to a Nexus file (plain-text or gzipped)

    Returns:
        dict of Tree: A dictionary of the trees represented by `nexus`, where keys are tree names (`str`) and values are `Tree` objects
    '''
    if nexus.lower().endswith('.gz'): # gzipped file
        f = gopen(nexus)
    elif isfile(nexus): # plain-text file
        f = open(nexus)
    else:
        f = nexus.splitlines()
    trees = dict()
    for line in f:
        if isinstance(line,bytes):
            l = line.decode().strip()
        else:
            l = line.strip()
        if l.lower().startswith('tree '):
            i = l.index('='); left = l[:i].strip(); right = l[i+1:].strip()
            name = ' '.join(left.split(' ')[1:])
            trees[name] = read_tree_newick(right)
    return trees