def pagerank(graph, damping=0.85, tolerance=1e-10, max_iterations=1000,
             history=None):
    nodes = list(graph)
    n = len(nodes)
    if n == 0:
        raise ValueError("The graph must contain at least one page.")

    scores = {node: 1.0 / n for node in nodes}

    for iteration in range(1, max_iterations + 1):
        dangling_mass = sum(
            scores[node] for node in nodes if not graph[node]
        )

        base = (1.0 - damping) / n + damping * dangling_mass / n
        updated = {node: base for node in nodes}

        for source in nodes:
            targets = graph[source]
            if targets:
                contribution = damping * scores[source] / len(targets)
                for target in targets:
                    updated[target] += contribution

        old_total = sum(scores.values())
        new_total = sum(updated.values())
        total_change = abs(new_total - old_total) / old_total
        score_change = sum(
            abs(updated[node] - scores[node]) for node in nodes
        )
        if history is not None:
            history.append((iteration, new_total, total_change,
                            score_change))

        scores = updated
        if total_change <= 0.005 and score_change <= tolerance:
            return scores, iteration

    raise RuntimeError("PageRank did not converge within the iteration limit.")


def closeness_centrality(graph):
    nodes = list(graph)
    n = len(nodes)
    if n <= 1:
        return {node: 0.0 for node in nodes}

    index = {node: i for i, node in enumerate(nodes)}
    adjacency = []
    for node in nodes:
        mask = 0
        for target in graph[node]:
            mask |= 1 << index[target]
        adjacency.append(mask)

    all_nodes = (1 << n) - 1
    result = {}

    for source, name in enumerate(nodes):
        seen = 1 << source
        frontier = seen
        depth = 0
        reached = 0
        distance_sum = 0

        while frontier and seen != all_nodes:
            neighbors = 0
            remaining = frontier

            while remaining:
                bit = remaining & -remaining
                vertex = bit.bit_length() - 1
                neighbors |= adjacency[vertex]
                remaining ^= bit

                if (neighbors | seen) == all_nodes:
                    break

            frontier = neighbors & ~seen
            depth += 1
            count = frontier.bit_count()
            reached += count
            distance_sum += depth * count
            seen |= frontier

        result[name] = (
            (reached / distance_sum) * (reached / (n - 1))
            if distance_sum else 0.0
        )

    return result
