""" Copyright (C) 2019 weak_ptr <weak_ptr@163.com> all rights reserved.

Based on better_exceptions.formatter
"""

from __future__ import absolute_import

import pdb
import sys

import six
import socketserver

import ast
import inspect
import os
import traceback
from locale import getpreferredencoding

PIPE_CHAR = u'\u2502'
CAP_CHAR = u'\u2514'

try:
    PIPE_CHAR = six.ensure_str(PIPE_CHAR, encoding=getpreferredencoding())
except UnicodeEncodeError:
    PIPE_CHAR = '|'
    CAP_CHAR = '->'


class LineCache(object):

    def __init__(self):
        self.cached = {}

    def get_line(self, filename, lineno):
        if filename not in self.cached:
            with open(filename) as f:
                self.cached[filename] = f.readlines()

        return self.cached[filename][lineno - 1]


cached_source = LineCache()

MAX_LENGTH = 128


class TracePoint(object):

    def __init__(self, cond_fn=None, call_fn=None):
        if cond_fn:
            self.cond = cond_fn
        if call_fn:
            print(call_fn)
            self.__call__ = call_fn

    def cond(self, frame, event, arg):
        raise NotImplementedError()

    def __call__(self, frame, event, arg):
        raise NotImplementedError()


class Tracer(object):
    do_at_line = []
    do_at_call = []
    do_at_return = []

    def dispatch(self, frame, event, arg):
        if event == 'call':
            self.at_call(frame, event, arg)
        elif event == 'line':
            self.at_line(frame, event, arg)
        elif event == 'return':
            self.at_return(frame, event, arg)
        else:
            return self.dispatch

    def at_line(self, frame, event, arg):
        for tp in self.do_at_line:
            if tp.cond(frame, event, arg):
                tp(frame, event, arg)

    def at_call(self, frame, event, arg):
        for tp in self.do_at_call:
            if tp.cond(frame, event, arg):
                tp(frame, event, arg)

    def at_return(self, frame, event, arg):
        for tp in self.do_at_return:
            if tp.cond(frame, event, arg):
                tp(frame, event, arg)


class CallStackFormatter(object):
    def __init__(self, max_length=MAX_LENGTH, pipe_char=PIPE_CHAR, cap_char=CAP_CHAR):
        self._max_length = max_length
        self._pipe_char = pipe_char
        self._cap_char = cap_char

    @staticmethod
    def get_relevant_names(tree):
        return [node for node in ast.walk(tree) if isinstance(node, ast.Name)]

    def format_value(self, v):
        v = repr(v)
        max_length = self._max_length
        if max_length is not None and len(v) > max_length:
            v = v[:max_length] + '...'
        return v

    def get_relevant_values(self, frame, tree):
        names = self.get_relevant_names(tree)
        values = []

        for name in names:
            text = name.id
            col = name.col_offset
            if text in frame.f_locals:
                val = frame.f_locals.get(text, None)
                values.append((text, col, self.format_value(val)))
            elif text in frame.f_globals:
                val = frame.f_globals.get(text, None)
                values.append((text, col, self.format_value(val)))

        values.sort(key=lambda e: e[1])

        return values

    def get_frame_infomation(self, frame):
        filename = frame.f_code.co_filename
        lineno = frame.f_lineno
        function = frame.f_code.co_name

        source = cached_source.get_line(filename, lineno)
        source = source.strip()

        try:
            tree = ast.parse(source, mode='exec')
        except SyntaxError:
            return filename, lineno, function, source, []

        relevant_values = self.get_relevant_values(frame, tree)

        return filename, lineno, function, source, relevant_values

    def format_frame(self, tb):
        filename, lineno, function, source, relevant_values = self.get_frame_infomation(tb)

        lines = [source]
        for i in reversed(range(len(relevant_values))):
            _, col, val = relevant_values[i]
            pipe_cols = [pcol for _, pcol, _ in relevant_values[:i]]
            line = ''
            index = 0
            for pc in pipe_cols:
                line += (' ' * (pc - index)) + self._pipe_char
                index = pc + 1

            if isinstance(val, six.binary_type) and six.PY2:
                # In Python2 the Non-ASCII value will be the escaped string,
                # use string-escape to decode the string to show the text in human way.
                val = six.ensure_text(val.decode("string-escape"))

            line += u'{}{} {}'.format((' ' * (col - index)), self._cap_char, val)
            lines.append(line)
        formatted = u'\n    '.join([six.ensure_text(x, encoding=getpreferredencoding()) for x in lines])

        return filename, lineno, function, formatted

    def format_stack(self, stack=None):
        stack = stack or inspect.stack()

        frames = []
        for f_info in stack:
            formatted = self.format_frame(f_info.frame)

            # special case to ignore runcode() here.
            if not (os.path.basename(formatted[0]) == 'code.py' and formatted[2] == 'runcode'):
                frames.append(formatted)

        frames.reverse()
        lines = traceback.format_list(frames)

        return ''.join(lines)


_tracer = Tracer()


class _TraceCall(TracePoint):

    def __init__(self, fn):
        super(_TraceCall, self).__init__()
        self.func_name = fn

    def cond(self, frame, event, arg):
        return frame.f_code.co_name == self.func_name

    def __call__(self, frame, event, arg):
        print_stack()


class _DebugCall(TracePoint):
    def __init__(self, debugger, func, once):
        super(_DebugCall, self).__init__()
        self.debugger = debugger
        self.func_name = func
        self.once = once

    def cond(self, frame, event, arg):
        return frame.f_code.co_name == self.func_name

    def __call__(self, *args, **kwargs):
        self.debugger.set_trace()


def print_stack():
    print(CallStackFormatter().format_stack())


def trace_call(func_name):
    global _tracer
    _tracer.do_at_call.append(_TraceCall(func_name))
    sys.settrace(_tracer.dispatch)


def debug_call(func, once):
    global _tracer
    _tracer.do_at_call.append(_DebugCall(pdb, func, once))
    sys.settrace(_tracer.dispatch)
