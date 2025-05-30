# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2014
#            IBM, 2023
#
# Authors: Ruda Moura <rmoura@redhat.com>
#          Lucas Meneghel Rodrigues <lmr@redhat.com>
#          Harish S <harisrir@linux.vnet.ibm.com>
#          Maram Srimannarayana Murthy <Maram.Srimannarayana.Murthy@ibm.com>
#

"""
This module contains handy classes that can be used inside
avocado core code or plugins.
"""


import math
import re
import sys


class InvalidDataSize(ValueError):
    """
    Signals that the value given to :class:`DataSize` is not valid.
    """


def ordered_list_unique(object_list):
    """
    Returns an unique list of objects, with their original order preserved
    """
    seen = set()
    seen_add = seen.add
    return [x for x in object_list if not (x in seen or seen_add(x))]


def geometric_mean(values):
    """
    Evaluates the geometric mean for a list of numeric values.
    This implementation is slower but allows unlimited number of values.
    :param values: List with values.
    :return: Single value representing the geometric mean for the list values.
    :see: http://en.wikipedia.org/wiki/Geometric_mean
    """
    try:
        values = [int(value) for value in values]
    except ValueError as exc:
        raise ValueError(f"Invalid inputs {values}. Provide valid inputs") from exc
    no_values = len(values)
    if not no_values:
        return None
    return math.exp(sum(math.log(number) for number in values) / no_values)


def compare_matrices(matrix1, matrix2, threshold=0.05):  # pylint: disable=R0912
    """
    Compare 2 matrices nxm and return a matrix nxm with comparison data and
    stats. When the first columns match, they are considered as header and
    included in the results intact.

    :param matrix1: Reference Matrix of floats; first column could be header.
    :param matrix2: Matrix that will be compared; first column could be header
    :param threshold: Any difference greater than this percent threshold will
                      be reported.
    :return: Matrix with the difference in comparison, number of improvements,
             number of regressions, total number of comparisons.
    """
    improvements = 0
    regressions = 0
    same = 0
    new_matrix = []

    for line1, line2 in zip(matrix1, matrix2):
        new_line = []
        elements = iter(zip(line1, line2))
        try:
            element1, element2 = next(elements)
        except StopIteration:  # no data in this row
            new_matrix.append(new_line)
            continue
        if element1 == element2:  # this column contains header
            new_line.append(element1)
            try:
                element1, element2 = next(elements)
            except StopIteration:
                new_matrix.append(new_line)
                continue
        while True:
            try:
                ratio = float(element2) / float(element1)
            except ZeroDivisionError:  # For 0s, allow exact match or error
                if not float(element2):
                    new_line.append(".")
                    same += 1
                else:
                    new_line.append(f"error_{element2}/{element1}")
                    improvements += 1
                try:
                    element1, element2 = next(elements)
                except StopIteration:
                    break
                continue
            if ratio < (1 - threshold):  # handling regression
                regressions += 1
                new_line.append(100 * ratio - 100)
            elif ratio > (1 + threshold):  # handling improvements
                improvements += 1
                new_line.append(f"+{100 * ratio - 100:.6g}")
            else:
                same += 1
                new_line.append(".")
            try:
                element1, element2 = next(elements)
            except StopIteration:
                break
        new_matrix.append(new_line)

    total = improvements + regressions + same
    return (new_matrix, improvements, regressions, total)


def comma_separated_ranges_to_list(string):
    """
    Provides a list from comma separated ranges

    :param string: string of comma separated range
    :return list: list of integer values in comma separated range
    """
    values = []
    for range_str in string.split(","):
        if "-" in range_str:
            start, end = range_str.split("-")
            values.extend(range(int(start), int(end) + 1))
        else:
            values.append(int(range_str))
    return values


def recursive_compare_dict(dict1, dict2, level="DictKey", diff_btw_dict=None):
    """
    Difference between two dictionaries are returned
    Dict values can be a dictionary, list and value

    :rtype: list or None
    """
    if diff_btw_dict is None:
        diff_btw_dict = []
    if isinstance(dict1, dict) and isinstance(dict2, dict):
        if dict1.keys() != dict2.keys():
            set1 = set(dict1.keys())
            set2 = set(dict2.keys())
            diff_btw_dict.append(f"{level} + {set1-set2} - {set2-set1}")
            common_keys = set1 & set2
        else:
            common_keys = set(dict1.keys())
        for k in common_keys:
            recursive_compare_dict(
                dict1[k], dict2[k], level=f"{level}.{k}", diff_btw_dict=diff_btw_dict
            )
        return diff_btw_dict
    if isinstance(dict1, list) and isinstance(dict2, list):
        if len(dict1) != len(dict2):
            diff_btw_dict.append(f"{level} + {len(dict1)} - {len(dict2)}")
        common_len = min(len(dict1), len(dict2))
        for i in range(common_len):
            recursive_compare_dict(
                dict1[i],
                dict2[i],
                level=f"{level}.{dict1[i]}",
                diff_btw_dict=diff_btw_dict,
            )
    else:
        if dict1 != dict2:
            diff_btw_dict.append(f"{level} - dict1 value:{dict1}, dict2 value:{dict2}")
    return None


class Borg:
    """
    Multiple instances of this class will share the same state.

    This is considered a better design pattern in Python than
    more popular patterns, such as the Singleton. Inspired by
    Alex Martelli's article mentioned below:

    :see: http://www.aleax.it/5ep.html
    """

    __shared_state = {}

    def __init__(self):
        self.__dict__ = self.__shared_state


class LazyProperty:
    """
    Lazily instantiated property.

    Use this decorator when you want to set a property that will only be
    evaluated the first time it's accessed. Inspired by the discussion in
    the Stack Overflow thread below:

    :see: http://stackoverflow.com/questions/15226721/
    """

    def __init__(self, f_get):
        self.f_get = f_get
        self.func_name = f_get.__name__

    def __get__(self, obj, cls):
        if obj is None:
            return None
        value = self.f_get(obj)
        setattr(obj, self.func_name, value)
        return value


class CallbackRegister:
    """
    Registers pickable functions to be executed later.
    """

    def __init__(self, name, log):
        """
        :param name: Human readable identifier of this register
        """
        self._name = name
        self._items = []
        self._log = log

    def register(self, func, args, kwargs, once=False):
        """
        Register function/args to be called on self.destroy()
        :param func: Pickable function
        :param args: Pickable positional arguments
        :param kwargs: Pickable keyword arguments
        :param once: Add unique (func,args,kwargs) combination only once
        """
        item = (func, args, kwargs)
        if not once or item not in self._items:
            self._items.append(item)

    def unregister(self, func, args, kwargs):
        """
        Unregister (func,args,kwargs) combination
        :param func: Pickable function
        :param args: Pickable positional arguments
        :param kwargs: Pickable keyword arguments
        """
        item = (func, args, kwargs)
        if item in self._items:
            self._items.remove(item)

    def run(self):
        """
        Call all registered function
        """
        while self._items:
            item = self._items.pop()
            try:
                func, args, kwargs = item
                func(*args, **kwargs)
            except:  # Ignore all exceptions pylint: disable=W0702
                self._log.error(
                    "%s failed to destroy %s:\n%s", self._name, item, sys.exc_info()[1]
                )

    def __del__(self):
        """
        :warning: Always call self.run() manually, this is not guaranteed
                  to be executed!
        """
        self.run()


def time_to_seconds(time):
    """
    Convert time in minutes, hours and days to seconds.
    :param time: Time, optionally including the unit (i.e. '10d')
    """
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if time is not None:
        try:
            unit = time[-1].lower()
            if unit in units:
                mult = units[unit]
                seconds = int(time[:-1]) * mult
            else:
                seconds = int(time)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid value '{time}' for time. Use a string "
                f"with the number and optionally the time unit "
                f"(s, m, h or d)."
            ) from exc
    else:
        seconds = 0
    return seconds


class DataSize:
    """
    Data Size object with builtin unit-converted attributes.

    :param data: Data size plus optional unit string. i.e. '10m'. No
                 unit string means the data size is in bytes.
    :type data: str
    """

    __slots__ = ["_value", "_unit"]

    MULTIPLIERS = {
        "b": 1,  # 2**0
        "k": 1024,  # 2**10
        "m": 1048576,  # 2**20
        "g": 1073741824,  # 2**30
        "t": 1099511627776,
    }  # 2**40

    def __init__(self, data):
        try:
            norm = str(data).strip().lower()
            match = re.match(r"^(\d+(\.\d+)?)(?:\s*([bkmgt]))?$", norm)
            if not match:
                raise ValueError

            self._value = float(match.group(1))
            self._unit = match.group(3) or "b"

            if self._unit not in self.MULTIPLIERS or self._value < 0:
                raise ValueError

        except ValueError as exc:
            raise InvalidDataSize(
                f"Invalid data size '{data}'. Use formats like '10M', '2.5G', or '100'."
            ) from exc

    @property
    def value(self):
        return self._value

    @property
    def unit(self):
        return self._unit

    @property
    def b(self):
        return self._value * self.MULTIPLIERS[self._unit]

    @property
    def k(self):
        return int(self._value * self.MULTIPLIERS[self._unit] / self.MULTIPLIERS["k"])

    @property
    def m(self):
        return int(self._value * self.MULTIPLIERS[self._unit] / self.MULTIPLIERS["m"])

    @property
    def g(self):
        return int(self._value * self.MULTIPLIERS[self._unit] / self.MULTIPLIERS["g"])

    @property
    def t(self):
        return int(self._value * self.MULTIPLIERS[self._unit] / self.MULTIPLIERS["t"])
