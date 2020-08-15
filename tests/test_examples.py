# BSD 3-Clause License; see https://github.com/jpivarski/radiowave-spaceman/blob/master/LICENSE

from __future__ import absolute_import

import radiowave_spaceman


def test_1():
    # decorating the function with a search for "dataset" associates a set
    # of the same name that lists every attribute reference in the function

    @radiowave_spaceman.decorator("dataset")
    def function(dataset, x, y):
        print(dataset.zero)
        x + y
        z = nonexistent_function(dataset.one.two + 123)
        return z

    # ("zero",) is a direct attribute of "dataset", ("one", "two") is nested
    assert function.dataset() == set([
        ("zero",),
        ("one",),
        ("one", "two"),
    ])


def test_2():
    # if two datasets need to be checked, just use the decorator twice (two passes)

    @radiowave_spaceman.decorator("dataset1")
    @radiowave_spaceman.decorator("dataset2")
    def function(dataset1, dataset2):
        dataset1.zero
        dataset2.one.two

    assert function.dataset1() == set([
        ("zero",),
    ])
    assert function.dataset2() == set([
        ("one",),
        ("one", "two"),
    ])


def test_3():
    # also catch attributes of "another_dataset", which is another reference to
    # the same "dataset", as well as "another_another_dataset", which is partially
    # evaluated

    @radiowave_spaceman.decorator("dataset")
    def function(dataset, x, y):
        another_dataset = dataset
        another_another_dataset = another_dataset.one
        another_another_dataset.two

    # ("one", "two") is from "dataset.one.two"
    assert function.dataset() == set([
        ("one",),
        ("one", "two"),
    ])


def test_4():
    # an attribute reference might come lexically BEFORE the assignment because
    # of dynamic typing, so the function is repeatedly scanned until there are
    # no new symbols left

    @radiowave_spaceman.decorator("dataset")
    def function(dataset, x, y):
        z = not_the_dataset
        for i in range(2):
            z.two
            z = dataset.one

    assert function.dataset() == set([
        ("one",),
        ("one", "two"),
    ])

def test_5():
    # attributes might be referenced in functions called by the decorated function

    def another_function(some):
        some.one

    another_thing = 999

    @radiowave_spaceman.decorator("dataset")
    def function(dataset, x, y):
        z = 123 + another_thing
        yet_another_function(123, dataset.x, dataset.y)
        another_function(some=dataset)
        another_another_function(123, some=dataset, other=999)

    # yet_another_function doesn't exist yet, so its references aren't observed
    assert function.dataset() == set([
        ("x",),
        ("y",),
        ("one",),
        ("two",),
    ])

    def yet_another_function(x, some, other):
        some.three
        other.four

    # yet_another_function exists now, so we see its references
    assert function.dataset() == set([
        ("x",),
        ("x", "three"),
        ("y",),
        ("y", "four"),
        ("one",),
        ("two",),
    ])


# another_another_function is defined in the global scope
# global scope is evaluated first, so its references are observed above
def another_another_function(x, other, some):
    y = x + some.two


def test_6():
    # in Python, only nested functions (and comprehensions) make nested scopes
    # nested scopes can overshadow symbol names; don't count them

    @radiowave_spaceman.decorator("dataset")
    def function(dataset):
        def shadowed(dataset):
            dataset.y

        def not_shadowed(other):
            dataset.z

        # lambdas can shadow, too
        lambda dataset: dataset.yy
        lambda q: dataset.zz

        dataset.x

    # y and yy are not included because they're attributes of a shadowed "dataset"
    assert function.dataset() == set([
        ("x",),
        ("z",),
        ("zz",),
    ])
