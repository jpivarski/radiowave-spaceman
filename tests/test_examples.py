# BSD 3-Clause License; see https://github.com/jpivarski/radiowave-spaceman/blob/master/LICENSE

from __future__ import absolute_import

import radiowave_spaceman
from radiowave_spaceman import Unknown


def test_1():
    # decorating the function with a search for "dataset" attaches a set
    # of the same name listing every attribute reference in the function

    @radiowave_spaceman.decorator("dataset")
    def function(dataset, x, y):
        print(dataset.zero)
        x + y
        z = dataset.one.two + 123
        return z

    assert function.dataset == set([
        ("zero",),
        ("one",),
        ("one", "two"),
    ])


def test_2():
    # if two attributes need to be tracked, use the decorator twice

    @radiowave_spaceman.decorator("dataset1")
    @radiowave_spaceman.decorator("dataset2")
    def function(dataset1, dataset2):
        dataset1.zero
        dataset2.one.two

    assert function.dataset1 == set([
        ("zero",),
    ])
    assert function.dataset2 == set([
        ("one",),
        ("one", "two"),
    ])


def test_3():
    # also catch assignments of the dataset (or partially evaluated dataset)
    # to other symbols

    @radiowave_spaceman.decorator("dataset")
    def function(dataset, x, y):
        another_dataset = dataset
        z = another_dataset.one
        z.two

    assert function.dataset == set([
        ("one",),
        ("one", "two"),
    ])


def test_4():
    # an attribute reference might come before the assignment because Python
    # is dynamically typed, so the function is repeatedly scanned until there
    # are no new symbols left

    @radiowave_spaceman.decorator("dataset")
    def function(dataset, x, y):
        z = not_the_dataset
        for i in range(2):
            z.two
            z = dataset.one

    assert function.dataset == set([
        ("one",),
        ("one", "two"),
    ])
