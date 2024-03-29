# Copyright (c) 2015, MapR Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from sahara.plugins import provisioning as p
from sahara.plugins import testutils as tu
import sahara_plugin_mapr.plugins.mapr.abstract.cluster_context as a_context
from sahara_plugin_mapr.plugins.mapr.domain import service as bs
from sahara_plugin_mapr.plugins.mapr.services.management import management
from sahara_plugin_mapr.plugins.mapr.services.maprfs import maprfs
from sahara_plugin_mapr.plugins.mapr.services.oozie import oozie
from sahara_plugin_mapr.plugins.mapr.services.yarn import yarn
from sahara_plugin_mapr.plugins.mapr.versions.v5_2_0_mrv2 import \
    version_handler
from sahara_plugin_mapr.tests.unit import base as b


class TestHandler(b.SaharaTestCase):
    def __init__(self, *args, **kwds):
        super(TestHandler, self).__init__(*args, **kwds)
        self.handler = version_handler.VersionHandler()
        self.cluster = self._get_cluster()

    def _get_cluster(self):
        i1 = tu.make_inst_dict('id_1', 'instance_1', '1.1.1.1')
        master_proc = [
            yarn.RESOURCE_MANAGER.ui_name,
            yarn.NODE_MANAGER.ui_name,
            yarn.HISTORY_SERVER.ui_name,
            maprfs.CLDB.ui_name,
            maprfs.FILE_SERVER.ui_name,
            oozie.OOZIE.ui_name,
            management.ZOOKEEPER.ui_name,
        ]

        master_ng = tu.make_ng_dict('master', 'large', master_proc, 1, [i1])
        cluster_configs = {
            'Service': {
                'key': 'value',
                'Service Version': '1.1',
            },
        }

        cluster = tu.create_cluster(
            name='test_cluster',
            project='large',
            plugin='mapr',
            version='5.2.0.mrv2',
            node_groups=[master_ng],
            cluster_configs=cluster_configs,
        )
        self.ng = cluster.node_groups[0]
        self.instance = self.ng.instances[0]
        return cluster

    def test_get_context(self):
        self.assertIsInstance(self.handler.get_context(self._get_cluster()),
                              a_context.AbstractClusterContext)

    def test_get_services(self):
        services = self.handler.get_services()
        for service in services:
            self.assertIsInstance(service, bs.Service)

    def test_get_np_dict(self):
        np_dict = self.handler.get_node_processes()
        self.assertIsNotNone(np_dict)
        self.assertIsInstance(np_dict, dict)
        for k, v in np_dict.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, list)
            self.assertNotEqual(0, len(v))

    def test_get_configs(self):
        configs = self.handler.get_configs()
        self.assertIsInstance(configs, list)
        for config in configs:
            self.assertIsInstance(config, p.Config)

    def test_get_version_configs(self):
        version_configs = self.handler._get_version_configs()
        self.assertIsInstance(version_configs, list)
        for conf in version_configs:
            self.assertIsInstance(conf, p.Config)
            self.assertNotEqual(0, len(conf.config_values))
            self.assertEqual('dropdown', conf.config_type)

    def test_get_configs_dict(self):
        configs_dict = self.handler.get_configs_dict()
        self.assertIsInstance(configs_dict, dict)
        for k, v in configs_dict.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, dict)

    def test_get_open_ports(self):
        ports_list = self.handler.get_open_ports(self.ng)
        self.assertIsNotNone(ports_list)
        self.assertIsInstance(ports_list, list)
        for port in ports_list:
            self.assertIsInstance(port, int)
