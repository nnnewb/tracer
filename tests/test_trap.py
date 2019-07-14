import logging

import coloredlogs

import tracer

coloredlogs.install(level=logging.DEBUG)


def function(a):
    b = a + 1
    return b


def test_trace_call_stack():
    tracer.trace_call('function')
    a = 10

    function(a)
