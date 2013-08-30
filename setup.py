#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import distutils
import platform
from setuptools import setup, find_packages

major, minor, micro = platform.python_version().split('.')

if major != '2' or minor not in ['6', '7']:
    raise Exception('unsupported version of python')

requires = ['docker-py >= 0.1.5']

data_files = [('/etc/comodit-agent/plugins', ['conf/docks.conf']),
              ('/etc/comodit-agent/alerts.d', ['conf/alerts.d/docks.conf']),
              ('/var/lib/comodit-agent/plugins/docker-plugin', ['docks.py', '__init__.py'])]

setup(
    name='comodit-agent-plugin-docker',
    version='0.1.0',
    description='Deploy docker containers with ComodIT.',
    author='Laurent Eschenauer',
    author_email='laurent.eschenauer@comodit.com',
    url='https://github.com/comodit/comodit-agent-plugin-docker',
    license='MIT License',
    packages=find_packages(),
    package_data={'': ['LICENSE', 'AUTHORS']},
    include_package_data=True,
    data_files=data_files,
    # http://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'License :: License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Operating System :: POSIX',
        'Topic :: Content Management',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Intended Audience :: Developers',
        'Development Status :: 3 - Alpha',
    ],
    install_requires=requires,
)
