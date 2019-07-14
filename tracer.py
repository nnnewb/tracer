""" Copyright (C) 2019 weak_ptr <weak_ptr@163.com> all rights reserved.

Based on better_exceptions.formatter
"""

from __future__ import absolute_import

import ast
import inspect
import logging
import os
import sys
import traceback
from locale import getpreferredencoding

import six

PIPE_CHAR = u'\u2502'
CAP_CHAR = u'\u2514'
logger = logging.getLogger(__name__)

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

    def __init__(self):
        self.executed = []
        self.trace_points = []

    def has_tracing(self, tp, frame, event, arg):
        if isinstance(tp['cond'], (six.text_type, six.string_types)):
            def cond(f, e, a):
                return e == tp['cond']
        else:
            cond = tp['cond']

        return tp.get('enabled', True) and cond(frame, event, arg)

    def do_tracing(self, tp, frame, event, arg):
        if 'callback' in tp and tp['callback'] and callable(tp['callback']):
            tp['callback'](frame, event, arg)
        else:
            logger.warning('invalid trace point callback: {}'.format(tp['callback']))

    def dispatch(self, frame, event, arg):
        for tp in self.trace_points:
            if self.has_tracing(tp, frame, event, arg):
                self.do_tracing(tp, frame, event, arg)
                self.executed.append(tp)

        for tp in self.executed:
            if 'once' in tp and tp['once']:
                try:
                    idx = self.trace_points.index(tp)
                    removed = self.trace_points.pop(idx)
                    logger.debug('remove trace point due to once executed: {}'.format(removed))
                except ValueError:
                    logger.warning('No executed trace point {} found in trace_points'.format(tp))

        if len(self.trace_points) == 0:
            logger.debug('No trace points exists, execution tracking disabled.')
            return None

        return self.dispatch

    def set_trace(self, func, once=False):
        def cond(frame, event, arg):
            if event == 'call':
                return frame.f_code.co_name == func

        self.trace_points.append({
            'cond': cond,
            'callback': lambda frame, event, arg: print_stack(inspect.getouterframes(frame)[1:]),
            'enabled': True,
            'once': once,
        })


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

    def get_relevant_values(self, frame, names):
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

    def get_frame_information(self, frame):
        filename = frame.f_code.co_filename
        lineno = frame.f_lineno
        function = frame.f_code.co_name

        source = cached_source.get_line(filename, lineno)
        source = source.strip()

        try:
            tree = ast.parse(source, mode='exec')
        except SyntaxError:
            return filename, lineno, function, source, []

        relevant_names = self.get_relevant_names(tree)
        relevant_values = self.get_relevant_values(frame, relevant_names)

        return filename, lineno, function, source, relevant_values

    def format_frame(self, frame):
        filename, lineno, function, source, relevant_values = self.get_frame_information(frame)

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


def _cond_enter_function(func):
    return lambda frame, event, arg: frame.f_code.co_name == func


def print_stack(stack):
    formatter = CallStackFormatter()

    if not stack:
        stack = inspect.stack()[1:]

    print(formatter.format_stack(stack))


def trace_call(func_name):
    global _tracer
    _tracer.set_trace(func_name)
    sys.settrace(_tracer.dispatch)
