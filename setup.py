from setuptools import setup
import os

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as f:
    README = f.read()

setup(
    name='tracer',
    version='0.1.0',
    author='weak_ptr',
    author_email='weak_ptr@163.com',
    url='https://github.com/nnnewb/tracer',
    py_modules=['tracer'],
    keywords='debug traceback',
    description='Trace your function call',
    long_description=README,
    python_requires='>= 3.6, >=2.7'
)
