import logging

import coloredlogs

import tracer

coloredlogs.install(level=logging.DEBUG)


def trap_in(a):
    print(a)
    b = a + 1
    print(b)


def test_debug():
    tracer.debug_call('trap_in', False)
    a = 10

    trap_in(a)


def test_trace_call_stack():
    tracer.trace_call('trap_in')
    a = 10

    trap_in(a)
