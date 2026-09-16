import pytest

from fle.commons.models.serializable_function import SerializableFunction

pytestmark = pytest.mark.no_factorio


class _Instance:
    def __init__(self, **variables):
        self.persistent_vars = dict(variables)
        self.log = print


def _declare(instance, source, name):
    namespace = {}
    exec(source, namespace)
    wrapper = SerializableFunction(namespace[name], instance)
    instance.persistent_vars[name] = wrapper
    return wrapper


def test_call_sees_updated_persistent_values_and_reuses_cache():
    instance = _Instance(x=1)
    read = _declare(instance, "def read():\n    return x\n", "read")

    assert read() == 1
    cached = read._cached_func
    assert read() == 1
    assert read._cached_func is cached

    instance.persistent_vars["x"] = 2
    assert read() == 2
    assert read._cached_func is not cached


def test_call_sees_in_place_mutations_and_global_rebinding():
    instance = _Instance(x=[1])
    read = _declare(instance, "def read():\n    return x\n", "read")
    assert read() == [1]

    instance.persistent_vars["x"].append(2)
    assert read() == [1, 2]

    inc = _declare(
        instance,
        "def inc():\n    global x\n    x = [x[0] + 1]\n    return x\n",
        "inc",
    )
    assert inc() == [2]
    instance.persistent_vars["x"] = inc._cached_func.__globals__["x"]
    assert inc() == [3]


def test_bind_invalidates_cached_function():
    first = _Instance(x=1)
    second = _Instance(x=2)
    read = _declare(first, "def read():\n    return x\n", "read")
    assert read() == 1

    read.bind(second)
    assert read() == 2
