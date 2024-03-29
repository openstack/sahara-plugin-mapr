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


import abc
import os
import re

import jinja2 as j2

import sahara.plugins.exceptions as e
import sahara.plugins.utils as utils
from sahara_plugin_mapr.i18n import _


class FileAttr(object, metaclass=abc.ABCMeta):
    def __init__(self, path, data, mode, owner):
        self.path = path
        self.data = data
        self.mode = mode
        self.owner = owner


class BaseConfigurationFile(object, metaclass=abc.ABCMeta):
    def __init__(self, file_name):
        self.f_name = file_name
        self._config_dict = dict()
        self._local_path = None
        self._remote_path = None
        self.mode = None
        self.owner = None

    @property
    def remote_path(self):
        return self._remote_path

    @remote_path.setter
    def remote_path(self, path):
        self._remote_path = os.path.join(path, self.f_name)

    @abc.abstractmethod
    def render(self):
        pass

    @abc.abstractmethod
    def parse(self, content):
        pass

    def fetch(self, instance):
        with instance.remote() as r:
            content = r.read_file_from(self.remote_path, run_as_root=True)
            self.parse(content)

    def load_properties(self, config_dict):
        for k, v in config_dict.items():
            self.add_property(k, v)

    def add_property(self, name, value):
        self._config_dict[name] = value

    def add_properties(self, properties):
        for prop in properties.items():
            self.add_property(*prop)

    def _get_config_value(self, name):
        return self._config_dict.get(name, None)

    def __repr__(self):
        return '<Configuration file %s>' % self.f_name


class HadoopXML(BaseConfigurationFile):
    def __init__(self, file_name):
        super(HadoopXML, self).__init__(file_name)

    def parse(self, content):
        configs = utils.parse_hadoop_xml_with_name_and_value(content)
        for cfg in configs:
            self.add_property(cfg["name"], cfg["value"])

    def render(self):
        return utils.create_hadoop_xml(self._config_dict)


class RawFile(BaseConfigurationFile):
    def __init__(self, file_name):
        super(RawFile, self).__init__(file_name)

    def render(self):
        return self._config_dict.get('content', '')

    def parse(self, content):
        self._config_dict.update({'content': content})


class PropertiesFile(BaseConfigurationFile):
    def __init__(self, file_name, separator='='):
        super(PropertiesFile, self).__init__(file_name)
        self.separator = separator

    def parse(self, content):
        for line in content.splitlines():
            prop = line.strip()
            if len(prop) == 0:
                continue
            if prop[0] in ['#', '!']:
                continue
            name_value = prop.split(self.separator, 1)
            name = name_value[0]
            # check whether the value is empty
            value = name_value[1] if (len(name_value) == 2) else ''
            self.add_property(name.strip(), value.strip())

    def render(self):
        lines = ['%s%s%s' % (k, self.separator, v) for k, v in
                 self._config_dict.items()]
        return "\n".join(lines) + '\n'


class TemplateFile(BaseConfigurationFile):
    def __init__(self, file_name):
        super(TemplateFile, self).__init__(file_name)
        self._template = None

    @staticmethod
    def _j2_render(template, arg_dict):
        if template:
            return template.render(arg_dict)
        else:
            raise e.PluginsInvalidDataException(
                _('Template object must be defined'))

    def render(self):
        return self._j2_render(self._template, self._config_dict)

    def parse(self, content):
        self._template = j2.Template(content)


class EnvironmentConfig(BaseConfigurationFile):
    def __init__(self, file_name):
        super(EnvironmentConfig, self).__init__(file_name)
        self._lines = []
        self._regex = re.compile(r'export\s+(\w+)=(.+)')
        self._tmpl = 'export %s="%s"'

    def parse(self, content):
        for line in content.splitlines():
            line = self._escape(line)
            match = self._regex.match(line)
            if match:
                name, value = match.groups()
                value = value.replace("\"", '')
                self._lines.append((name, value))
                self.add_property(name, value)
            else:
                self._lines.append(line)

    @staticmethod
    def _escape(string):
        try:
            string = string.decode("utf-8")
        except AttributeError:
            pass
        string = str(string).strip()
        string = string.replace("\"", "")
        return string

    def render(self):
        result = []
        for line in self._lines:
            if isinstance(line, tuple):
                name, value = line
                args = (name, self._config_dict.get(name) or value)
                result.append(self._tmpl % args)
                if name in self._config_dict:
                    del self._config_dict[name]
            else:
                result.append(line)
        extra_ops = [self._tmpl % i for i in self._config_dict.items()]
        return '\n'.join(result + extra_ops) + '\n'
