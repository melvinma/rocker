# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import docker
import em
import unittest
import pexpect


from io import BytesIO as StringIO

from rocker.cli import DockerImageGenerator
from rocker.cli import list_plugins
from rocker.core import get_docker_client
from test_extension import plugin_load_parser_correctly

class NvidiaTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        client = get_docker_client()
        self.dockerfile_tags = []
        for distro_version in ['xenial', 'bionic']:
            dockerfile = """
FROM ubuntu:%(distro_version)s

RUN apt-get update && apt-get install glmark2 -y && apt-get clean

CMD glmark2 --validate
"""
            dockerfile_tag = 'testfixture_%s_glmark2' % distro_version
            iof = StringIO((dockerfile % locals()).encode())
            im = client.build(fileobj = iof, tag=dockerfile_tag)
            for e in im:
                pass
                #print(e)
            self.dockerfile_tags.append(dockerfile_tag)

    def setUp(self):
        # Work around interference between empy Interpreter
        # stdout proxy and test runner. empy installs a proxy on stdout
        # to be able to capture the information.
        # And the test runner creates a new stdout object for each test.
        # This breaks empy as it assumes that the proxy has persistent
        # between instances of the Interpreter class
        # empy will error with the exception
        # "em.Error: interpreter stdout proxy lost"
        em.Interpreter._wasProxyInstalled = False

    def test_nvidia_extension_basic(self):
        plugins = list_plugins()
        nvidia_plugin = plugins['nvidia']
        self.assertEqual(nvidia_plugin.get_name(), 'nvidia')    
        self.assertTrue(plugin_load_parser_correctly(nvidia_plugin))
        
        p = nvidia_plugin()
        mock_cliargs = {'base_image': 'ubuntu:xenial'}
        snippet = p.get_snippet(mock_cliargs)

        self.assertIn('COPY --from=glvnd /usr/local/lib/x86_64-linux-gnu /usr/local/lib/x86_64-linux-gnu', snippet)
        self.assertIn('COPY --from=glvnd /usr/local/lib/i386-linux-gnu /usr/local/lib/i386-linux-gnu', snippet)
        self.assertIn('ENV LD_LIBRARY_PATH /usr/local/lib/x86_64-linux-gnu:/usr/local/lib/i386-linux-gnu', snippet)
        self.assertIn('NVIDIA_VISIBLE_DEVICES', snippet)
        self.assertIn('NVIDIA_DRIVER_CAPABILITIES', snippet)

        mock_cliargs = {'base_image': 'ubuntu:bionic'}
        snippet = p.get_snippet(mock_cliargs)
        self.assertIn('RUN apt-get update && apt-get install -y --no-install-recommends', snippet)
        self.assertIn(' libglvnd0 ', snippet)
        self.assertIn(' libgles2 ', snippet)
        self.assertIn('COPY --from=glvnd /usr/share/glvnd/egl_vendor.d/10_nvidia.json /usr/share/glvnd/egl_vendor.d/10_nvidia.json', snippet)

        self.assertIn('NVIDIA_VISIBLE_DEVICES', snippet)
        self.assertIn('NVIDIA_DRIVER_CAPABILITIES', snippet)


        preamble = p.get_preamble(mock_cliargs)
        self.assertIn('FROM nvidia/opengl:1.0-glvnd-devel-', preamble)

        docker_args = p.get_docker_args(mock_cliargs)
        self.assertIn(' -e DISPLAY -e TERM', docker_args)
        self.assertIn(' -e QT_X11_NO_MITSHM=1', docker_args)
        self.assertIn(' -e XAUTHORITY=', docker_args)
        self.assertIn(' -v /tmp/.X11-unix:/tmp/.X11-unix ', docker_args)
        self.assertIn(' -v /etc/localtime:/etc/localtime:ro ', docker_args)
        self.assertIn(' --runtime=nvidia ', docker_args)
        self.assertIn(' --security-opt seccomp=unconfined', docker_args)

    
    def test_no_nvidia_glmark2(self):
        for tag in self.dockerfile_tags:
            dig = DockerImageGenerator([], {}, tag)
            self.assertEqual(dig.build(), 0)
            self.assertNotEqual(dig.run(), 0)

    def test_nvidia_glmark2(self):
        plugins = list_plugins()
        desired_plugins = ['nvidia', 'user']
        active_extensions = [e() for e in plugins.values() if e.get_name() in desired_plugins]
        for tag in self.dockerfile_tags:
            dig = DockerImageGenerator(active_extensions, {}, tag)
            self.assertEqual(dig.build(), 0)
            self.assertEqual(dig.run(), 0)
