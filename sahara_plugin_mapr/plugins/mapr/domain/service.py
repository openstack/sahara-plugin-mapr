# Copyright (c) 2015, MapR Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


from oslo_log import log as logging
from oslo_serialization import jsonutils as json

import sahara.plugins.exceptions as ex
import sahara.plugins.provisioning as p
from sahara.plugins import utils
from sahara_plugin_mapr.i18n import _
from sahara_plugin_mapr.plugins.mapr.util import commands as cmd
from sahara_plugin_mapr.plugins.mapr.util import event_log as el
from sahara_plugin_mapr.plugins.mapr.util import general as g
from sahara_plugin_mapr.plugins.mapr.util import service_utils as su

LOG = logging.getLogger(__name__)

SERVICE_UI = 'Web UI'

_INSTALL_PACKAGES_TIMEOUT = 3600


class Service(object, metaclass=g.Singleton):
    def __init__(self):
        self._name = None
        self._ui_name = None
        self._node_processes = []
        self._version = None
        self._dependencies = []
        self._ui_info = []
        self._cluster_defaults = []
        self._node_defaults = []
        self._validation_rules = []
        self._priority = 1

    @property
    def name(self):
        return self._name

    @property
    def ui_name(self):
        return self._ui_name

    @property
    def version(self):
        return self._version

    @property
    def node_processes(self):
        return self._node_processes

    @property
    def dependencies(self):
        return self._dependencies

    @property
    def cluster_defaults(self):
        return self._cluster_defaults

    @property
    def node_defaults(self):
        return self._node_defaults

    @property
    def validation_rules(self):
        return self._validation_rules

    def get_ui_info(self, cluster_context):
        return self._ui_info

    def install(self, cluster_context, instances):
        service_instances = cluster_context.filter_instances(instances,
                                                             service=self)

        @el.provision_step(_("Install %s service") % self.ui_name,
                           cluster_context_reference=0, instances_reference=1)
        def _install(_context, _instances):
            g.execute_on_instances(_instances,
                                   self._install_packages_on_instance,
                                   _context)
        if service_instances:
            _install(cluster_context, service_instances)

    @el.provision_event(instance_reference=1)
    def _install_packages_on_instance(self, instance, cluster_context):
        processes = [p for p in self.node_processes if
                     p.ui_name in instance.node_group.node_processes]
        if processes is not None and len(processes) > 0:
            packages = self._get_packages(cluster_context, processes)
            cmd = cluster_context.distro.create_install_cmd(packages)
            with instance.remote() as r:
                r.execute_command(cmd, run_as_root=True,
                                  timeout=_INSTALL_PACKAGES_TIMEOUT)

    def _get_packages(self, cluster_context, node_processes):
        result = []

        result += self.dependencies
        result += [(np.package, self.version) for np in node_processes]

        return result

    def _set_service_dir_owner(self, cluster_context, instances):
        service_instances = cluster_context.filter_instances(instances,
                                                             service=self)
        LOG.debug("Changing %s service dir owner", self.ui_name)
        for instance in service_instances:
            cmd.chown(instance, 'mapr:mapr', self.service_dir(cluster_context))

    def post_install(self, cluster_context, instances):
        pass

    def post_start(self, cluster_context, instances):
        pass

    def configure(self, cluster_context, instances=None):
        pass

    def update(self, cluster_context, instances=None):
        pass

    def get_file_path(self, file_name):
        template = 'plugins/mapr/services/%(service)s/resources/%(file_name)s'
        args = {'service': self.name, 'file_name': file_name}
        return template % args

    def get_configs(self):
        result = []

        for d_file in self.cluster_defaults:
            data = self._load_config_file(self.get_file_path(d_file))
            result += [self._create_config_obj(c, self.ui_name) for c in data]

        for d_file in self.node_defaults:
            data = self._load_config_file(self.get_file_path(d_file))
            result += [self._create_config_obj(c, self.ui_name, scope='node')
                       for c in data]

        return result

    def get_configs_dict(self):
        result = dict()
        for conf_obj in self.get_configs():
            result.update({conf_obj.name: conf_obj.default_value})
        return {self.ui_name: result}

    def _load_config_file(self, file_path=None):
        return json.loads(utils.get_file_text(file_path, 'sahara_plugin_mapr'))

    def get_config_files(self, cluster_context, configs, instance=None):
        return []

    def _create_config_obj(self, item, target='general', scope='cluster',
                           high_priority=False):
        def _prepare_value(value):
            if isinstance(value, str):
                return value.strip().lower()
            return value

        conf_name = _prepare_value(item.get('name', None))

        conf_value = _prepare_value(item.get('value', None))

        if not conf_name:
            raise ex.HadoopProvisionError(_("Config missing 'name'"))

        if conf_value is None:
            raise ex.PluginInvalidDataException(
                _("Config '%s' missing 'value'") % conf_name)

        if high_priority or item.get('priority', 2) == 1:
            priority = 1
        else:
            priority = 2

        return p.Config(
            name=conf_name,
            applicable_target=target,
            scope=scope,
            config_type=item.get('config_type', "string"),
            config_values=item.get('config_values', None),
            default_value=conf_value,
            is_optional=item.get('is_optional', True),
            description=item.get('description', None),
            priority=priority)

    def get_version_config(self, versions):
        return p.Config(
            name='%s Version' % self._ui_name,
            applicable_target=self.ui_name,
            scope='cluster',
            config_type='dropdown',
            config_values=[(v, v) for v in sorted(versions, reverse=True)],
            is_optional=False,
            description=_('Specify the version of the service'),
            priority=1)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            version_eq = self.version == other.version
            ui_name_eq = self.ui_name == other.ui_name
            return version_eq and ui_name_eq
        return NotImplemented

    def restart(self, instances):
        for node_process in self.node_processes:
            filtered_instances = su.filter_by_node_process(instances,
                                                           node_process)
            if filtered_instances:
                node_process.restart(filtered_instances)

    def service_dir(self, cluster_context):
        args = {'mapr_home': cluster_context.mapr_home, 'name': self.name}
        return '%(mapr_home)s/%(name)s' % args

    def home_dir(self, cluster_context):
        args = {
            'service_dir': self.service_dir(cluster_context),
            'name': self.name,
            'version': self.version,
        }
        return '%(service_dir)s/%(name)s-%(version)s' % args

    def conf_dir(self, cluster_context):
        return '%s/conf' % self.home_dir(cluster_context)

    def post_configure_sh(self, cluster_context, instances):
        pass

    def post_configure(self, cluster_context, instances):
        pass
