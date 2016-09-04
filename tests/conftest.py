#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
# The MIT License
#
# Copyright (c) 2016 Grigory Chernyshev
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
###############################################################################

import os
import sys
import time
import copy
import shutil
import subprocess

import mock
import pytest
import requests
from vcr import VCR
from yagocd import Yagocd
from yagocd.session import Session

TESTING_VERSIONS = [
    '16.1.0',
    '16.2.1',
    '16.3.0',
    '16.6.0',
    '16.7.0',
    '16.8.0',
    '16.9.0',
]


@pytest.fixture(scope='session')
def tests_dir():
    return os.path.dirname(os.path.realpath(__file__))


@pytest.fixture()
def mock_session():
    session = mock.patch('yagocd.session.Session').start()
    session.server_url = 'http://example.com'
    return session


@pytest.fixture(scope="class")
def session_fixture():
    options = copy.deepcopy(Yagocd.DEFAULT_OPTIONS)
    options['server'] = 'http://localhost:8153/'
    return Session(
        auth=('admin', '12345'),
        options=options
    )


root_cassette_library_dir = os.path.join(tests_dir(), 'fixtures/cassettes')


@pytest.fixture()
def my_vcr(gocd_docker):
    return VCR(
        path_transformer=VCR.ensure_suffix('.yaml'),
        cassette_library_dir=os.path.join(root_cassette_library_dir, gocd_docker),
    )


CONTAINER_NAME = 'yagocd-server'
CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


def pytest_addoption(parser):
    parser.addoption(
        "--fresh-run", action="store_true", default=False,
        help=(
            "Execute fresh run of tests: all cassettes will be deleted, instance of GoCD will be "
            "started in Docker container and test would be executed upon it."
        )
    )


@pytest.fixture(scope='session')
def fresh_run(request):
    return request.config.getoption("--fresh-run")


@pytest.fixture(scope="session", params=TESTING_VERSIONS)
def gocd_docker(request, fresh_run):
    if fresh_run:
        cassette_library_dir = os.path.join(root_cassette_library_dir, request.param)
        if os.path.exists(cassette_library_dir):
            print("Removing existing cassettes...")
            shutil.rmtree(cassette_library_dir)

        start_container(version_tag=request.param)
        wait_till_started()

        def fin():
            stop_container()

        request.addfinalizer(fin)
    return request.param


def start_container(version_tag):
    sys.stdout.write('Starting Docker container [{} version]...'.format(version_tag))
    output = subprocess.check_output([
        "/usr/local/bin/docker",
        "ps",
        "--quiet",
        "--filter=name={container_name}".format(
            container_name=CONTAINER_NAME),
    ])

    if not output:
        subprocess.check_call([
            "/usr/local/bin/docker",
            "run",
            "-p=8153:8153",
            "-p=8154:8154",
            "--detach",
            "--volume={current_dir}/docker:/workspace".format(
                current_dir=CURRENT_DIR
            ),
            "--workdir=/workspace",
            "--name={container_name}".format(
                container_name=CONTAINER_NAME
            ),
            "gocd/gocd-dev:{tag}".format(tag=version_tag),
            "/bin/bash",
            "-c",
            "'/workspace/bootstrap.sh'",
        ])


def wait_till_started():
    sys.stdout.write('Waiting for availability of GoCD in Docker.')
    while True:
        try:
            requests.get("http://localhost:8153/go")
        except requests.exceptions.ConnectionError:
            sys.stdout.write('.')
            time.sleep(5)
        else:
            break


def stop_container():
    subprocess.check_call([
        "/usr/local/bin/docker",
        "rm",
        "-f",
        CONTAINER_NAME
    ])
