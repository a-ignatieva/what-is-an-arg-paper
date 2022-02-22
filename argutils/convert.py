import collections

import pandas as pd
import networkx as nx
import numpy as np
import tskit

import argutils


def convert_argweaver(infile):
    """
    Convert an ARGweaver .arg file to a tree sequence. An example .arg file is at

    https://github.com/CshlSiepelLab/argweaver/blob/master/test/data/test_trans/0.arg
    """
    start, end = next(infile).strip().split()
    assert start.startswith("start=")
    start = int(start[len("start=") :])
    assert end.startswith("end=")
    end = int(end[len("end=") :])
    # the "name" field can be a string. Force it to be so, in case it is just numbers
    df = pd.read_csv(infile, header=0, sep="\t", dtype={"name": str, "parents": str})

    name_to_record = {}
    for _, row in df.iterrows():
        row = dict(row)
        name_to_record[row["name"]] = row
    # We could use nx to do this, but we want to be sure the order is correct.
    parent_map = collections.defaultdict(list)

    # Make an nx DiGraph so we can do a topological sort.
    G = nx.DiGraph()
    for row in name_to_record.values():
        child = row["name"]
        parents = row["parents"]
        G.add_node(child)
        if isinstance(parents, str):
            for parent in row["parents"].split(","):
                G.add_edge(child, parent)
                parent_map[child].append(parent)

    tables = tskit.TableCollection(sequence_length=end)
    tables.nodes.metadata_schema = tskit.MetadataSchema.permissive_json()
    breakpoints = np.full(len(G), tables.sequence_length)
    aw_to_tsk_id = {}
    for node in nx.topological_sort(G):
        record = name_to_record[node]
        flags = 0
        if node.startswith("n"):
            flags = tskit.NODE_IS_SAMPLE
            assert record["age"] == 0
            assert record["event"] == "gene"
            time = 0
        else:
            # Use topological sort order for age for the moment.
            time += 1
        tsk_id = tables.nodes.add_row(flags=flags, time=time, metadata=record)
        aw_to_tsk_id[node] = tsk_id
        if record["event"] == "recomb":
            breakpoints[tsk_id] = record["pos"]

    L = tables.sequence_length
    for aw_node in G:
        child = aw_to_tsk_id[aw_node]
        parents = [aw_to_tsk_id[aw_parent] for aw_parent in parent_map[aw_node]]
        if len(parents) == 1:
            tables.edges.add_row(0, L, parents[0], child)
        elif len(parents) == 2:
            # Recombination node.
            # If we wanted a GARG here we'd add an extra node
            x = breakpoints[child]
            tables.edges.add_row(0, x, parents[0], child)
            tables.edges.add_row(x, L, parents[1], child)
        else:
            assert len(parents) == 0
    # print(tables)
    tables.sort()
    # print(tables)
    ts = tables.tree_sequence()
    # The plan here originally was to use the earg_to_garg method to
    # convert the recombination events to two parents (making a
    # standard GARG). However, there are some complexities here so
    # returning the ARG topology as defined for now. There is an
    # argument that we should do this anyway, since that's the structure
    # that was returned and makes very little difference.

    # garg = argutils.earg_to_garg(ts)

    return ts.simplify(keep_unary=True)