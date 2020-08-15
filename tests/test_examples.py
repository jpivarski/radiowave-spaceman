# BSD 3-Clause License; see https://github.com/jpivarski/radiowave-spaceman/blob/master/LICENSE

from __future__ import absolute_import

import radiowave_spaceman


def test_1():
    @radiowave_spaceman.decorator("dataset")
    def function(dataset, x, y):
        dataset.zero
        x + y
        dataset.one.two
        return z

    assert function.dataset == set([
        ("zero",),
        ("one",),
        ("one", "two"),
    ])


# def test_2():
#     @radiowave_spaceman.decorator("dataset")
#     def function(dataset, x, y):
#         dataset.zero
#         x + y
#         dataset.one.two
#         return z

#     print(function.dataset)
#     raise Exception
