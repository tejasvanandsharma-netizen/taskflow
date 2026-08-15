"""TaskFlow Section 2 automated checks.

Run from the repository root:

    python check_algorithms.py

Prints one PASS/FAIL line per check and exits non-zero if anything fails.
"""

from backend.algorithms import (
    binary_search,
    binary_search_count,
    insertion_sort,
    insertion_sort_count,
    linear_search_count,
)


def main():
    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print("PASS - " + name)
        else:
            failed += 1
            print("FAIL - " + name)

    # insertion_sort on an empty list
    empty = []
    insertion_sort(empty, "priority")
    check("insertion_sort on empty list does not error", empty == [])

    # insertion_sort on a single-element list
    single = [{"id": 1, "priority": 2}]
    insertion_sort(single, "priority")
    check("insertion_sort on single-element list", single == [{"id": 1, "priority": 2}])

    # binary_search finding first, middle, last elements
    index = [{"id": i, "title": chr(97 + i)} for i in range(5)]  # a..e
    check("binary_search finds first element", binary_search(index, "a", "title") == 0)
    check("binary_search finds middle element", binary_search(index, "c", "title") == 2)
    check("binary_search finds last element", binary_search(index, "e", "title") == 4)

    # binary_search returns not-found for an absent value
    check("binary_search returns -1 for absent value", binary_search(index, "z", "title") == -1)

    # insertion_sort_count returns int > 0 and sorts correctly
    records = [
        {"id": 3, "priority": 3},
        {"id": 1, "priority": 1},
        {"id": 2, "priority": 2},
    ]
    count = insertion_sort_count(records, "priority")
    check("insertion_sort_count returns int > 0", isinstance(count, int) and count > 0)
    check("insertion_sort_count sorts correctly",
          [r["priority"] for r in records] == [1, 2, 3])

    # binary_search_count returns correct index and count > 0
    index10 = [{"id": i, "title": chr(97 + i)} for i in range(10)]
    result = binary_search_count(index10, "e", "title")
    check("binary_search_count returns correct index", result["index"] == 4)
    check("binary_search_count returns count > 0", result["comparison_count"] > 0)

    # linear_search_count for an absent value returns count == list length
    records2 = [{"title": "a"}, {"title": "b"}, {"title": "c"}]
    result2 = linear_search_count(records2, "zz", "title")
    check("linear_search_count absent value count == length",
          result2["index"] == -1 and result2["comparison_count"] == len(records2))

    print("-" * 40)
    print(f"TOTAL: {passed} passed, {failed} failed")
    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
