"""TaskFlow Section 2: hand-rolled sorting and searching algorithms.

All functions operate on lists of dictionaries, sorted by the value stored at
``record[key]``. Nothing here calls Python's built-in ``sort()``/``sorted()``.
"""

PRIORITY_WEIGHTS = {"low": 1, "medium": 2, "high": 3}


def insertion_sort(records, key):
    """Sort ``records`` (a list of dicts) in place by the value at ``record[key]``.

    Mutates ``records`` directly and returns ``None``.
    """
    for i in range(1, len(records)):
        current = records[i]
        j = i - 1
        while j >= 0 and records[j][key] > current[key]:
            records[j + 1] = records[j]
            j -= 1
        records[j + 1] = current


def binary_search(sorted_records, target_value, key):
    """Return the index of a record whose ``record[key] == target_value``, else -1.

    ``sorted_records`` must already be sorted by ``key``. Standard low/high/mid
    pointer loop.
    """
    lo, hi = 0, len(sorted_records) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if sorted_records[mid][key] == target_value:
            return mid
        if sorted_records[mid][key] < target_value:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def linear_search(records, target_value, key):
    """Return the index of the first record whose ``record[key] == target_value``.

    Scans every record in order. Returns -1 if absent.
    """
    for i, record in enumerate(records):
        if record[key] == target_value:
            return i
    return -1


def insertion_sort_count(records, key):
    """Sort ``records`` in place by ``key`` while counting comparisons.

    Returns the comparison count as an integer.
    """
    comparison_count = 0
    for i in range(1, len(records)):
        current = records[i]
        j = i - 1
        while j >= 0:
            comparison_count += 1
            if records[j][key] <= current[key]:
                break
            records[j + 1] = records[j]
            j -= 1
        records[j + 1] = current
    return comparison_count


def binary_search_count(sorted_records, target_value, key):
    """Like ``binary_search`` but returns {"index": ..., "comparison_count": ...}."""
    lo, hi = 0, len(sorted_records) - 1
    comparison_count = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        comparison_count += 1
        if sorted_records[mid][key] == target_value:
            return {"index": mid, "comparison_count": comparison_count}
        if sorted_records[mid][key] < target_value:
            lo = mid + 1
        else:
            hi = mid - 1
    return {"index": -1, "comparison_count": comparison_count}


def linear_search_count(records, target_value, key):
    """Like ``linear_search`` but returns {"index": ..., "comparison_count": ...}."""
    for i, record in enumerate(records):
        if record[key] == target_value:
            return {"index": i, "comparison_count": i + 1}
    return {"index": -1, "comparison_count": len(records)}
