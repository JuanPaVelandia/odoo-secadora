# -*- coding: utf-8 -*-

from itertools import chain


def _boundaries(intervals, opening, closing):
    for start, stop, recs in intervals:
        if start < stop:
            yield (start, opening, recs)
            yield (stop, closing, recs)


class Intervals:
    """Compatibility replacement for the legacy resource Intervals helper."""

    def __init__(self, intervals=()):
        self._items = []
        if intervals:
            append = self._items.append
            starts = []
            recses = []
            boundaries = sorted(
                _boundaries(sorted(intervals), "start", "stop"),
                key=lambda item: (item[0], 0 if item[1] == "start" else 1),
            )
            for value, flag, recs in boundaries:
                if flag == "start":
                    starts.append(value)
                    recses.append(recs)
                else:
                    start = starts.pop()
                    if not starts:
                        append((start, value, recses[0].union(*recses)))
                        recses.clear()

    def __bool__(self):
        return bool(self._items)

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __reversed__(self):
        return reversed(self._items)

    def __or__(self, other):
        return Intervals(chain(self._items, other._items))

    def __and__(self, other):
        return self._merge(other, difference=False)

    def __sub__(self, other):
        return self._merge(other, difference=True)

    def _merge(self, other, difference):
        result = Intervals()
        append = result._items.append

        bounds1 = _boundaries(sorted(self), "start", "stop")
        bounds2 = _boundaries(sorted(other), "switch", "switch")

        start = None
        recs1 = None
        enabled = difference
        for value, flag, recs in sorted(chain(bounds1, bounds2), key=lambda item: item[0]):
            if flag == "start":
                start = value
                recs1 = recs
            elif flag == "stop":
                if enabled and start < value:
                    append((start, value, recs1))
                start = None
            else:
                if not enabled and start is not None:
                    start = value
                if enabled and start is not None and start < value:
                    append((start, value, recs1))
                enabled = not enabled

        return result


def sum_intervals(intervals):
    return sum((stop - start).total_seconds() / 3600 for start, stop, _records in intervals)
