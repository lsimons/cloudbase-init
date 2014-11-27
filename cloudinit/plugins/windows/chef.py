#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2014 Leo Simons
#
#    Author: Avishai Ish-Shalom <avishai@fewbytes.com>
#    Author: Mike Moulton <mike@meltmedia.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Leo Simons <lsimons@schubergphilis.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Copyright 2013 Cloudbase Solutions Srl
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
**Summary:** plugin that configures, starts and installs chef.

**Description:** This plugin enables chef to be installed (from msi).
Before this occurs chef configurations are
written to disk (validation.pem, client.pem, first-boot.json, client.rb),
and needed chef folders/directories are created (C:\chef
and so-on). Then once installing proceeds correctly if configured chef will
be started (in daemon mode or in non-daemon mode) and then once that has
finished (if ran in non-daemon mode this will be when chef finishes
converging, if ran in daemon mode then no further actions are possible since
chef will have forked into its own process) then a post run function can
run that can do finishing activities (such as removing the validation pem
file).

It can be configured with the following option structure::

    chef:
       directories: (optional, directories to create)
       validation_key or validation_cert: (optional string to be written to
                                           C:\chef\validation.pem)
       firstboot_path: (path to write run_list and initial_attributes keys that
                        should also be present in this configuration, defaults
                        to C:\first-boot.json)
       exec: boolean to run or not run chef (defaults to true)
       msi_url: url from which to download the chef msi

    chef.rb template keys (if falsey, then will be skipped and not
                           written to C:\chef\client.rb):

    chef:
      client_key:
      environment:
      file_backup_path:
      file_cache_path:
      json_attribs:
      log_level:
      log_location:
      node_name:
      server_url:
      show_time:
      ssl_verify_mode:
      validation_key:
      validation_name:
"""

import itertools
import json
import os

from oslo.config import cfg

from cloudinit import templater
from cloudinit import url_helper
from cloudinit.util import get_cfg_option_bool, get_cfg_option_str, get_cfg_option_list, make_header
from cloudinit.util import ensure_dir, ensure_dirs, write_file
from cloudinit.util import subp, get_cfg_option_int, tempdir
from cloudbaseinit.openstack.common import log as logging
from cloudbaseinit.plugins import base


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class ChefBootstrapPlugin(base.BasePlugin):
    """
    Version of cloudinit.config.cc_chef that works with
    cloudbase-init.
    """

    def execute(self, service, shared_data):
        instance_id = service.get_instance_id()
        if not instance_id:
            LOG.debug('Instance ID not found in metadata')
            return base.PLUGIN_EXECUTE_ON_NEXT_BOOT, False
        chef_cfg = {
            "instance_id": instance_id
        }
        chef_cfg.update(shared_data)
        user_data = service.get_user_data()
        user_data = json.loads(user_data.decode('utf8'))
        chef_cfg.update(user_data)

        handle(chef_cfg, LOG)

        if is_installed():
            return base.PLUGIN_EXECUTION_DONE, False
        else:
            return base.PLUGIN_EXECUTE_ON_NEXT_BOOT, False

# todo what's a nice flexible way to fill this in?
TEMPLATE_PATH_BASE = "C:\\Program Files (x86)\\Cloudbase Solutions\\Cloudbase-Init\\" \
                     "Python27\\Lib\\site-packages\\cloudinit"
# todo what's a nice flexible way to fill this in?
CHEF_SERVER = "betachef.schubergphilis.com"
PLATFORM_VERSION = "2012r2"
PLATFORM_ARCHITECTURE = "x86_64"
CHEF_VERSION = "11.14.2-1"
MSI_URL = "https://%s/chef-guard/download?p=windows&pv=%s&m=%s&v=%s" % (
    CHEF_SERVER,
    PLATFORM_VERSION,
    PLATFORM_ARCHITECTURE,
    CHEF_VERSION
)
MSI_URL_RETRIES = 5


###########
# code from cloudinit.config.cc_chef
###########
CHEF_DIRS = tuple([
    'C:\\chef',
    'C:\\chef\\cache',
    'C:\\opscode\\chef',
    'C:\\opscode\\chef\\bin',
    'C:\\opscode\\chef\\embedded',
    'C:\\opscode\\chef\\embedded\\bin',
    'C:\\opscode\\chef\\embedded\\etc',
    'C:\\opscode\\chef\\embedded\\lib',
])
REQUIRED_CHEF_DIRS = tuple([
    'C:\\chef',
])

CHEF_VALIDATION_PEM_PATH = 'C:\\etc\chef\\validation.pem'
CHEF_FB_PATH = 'C:\\etc\chef\\first-boot.json'
CHEF_RB_TPL_DEFAULTS = {
    # These are ruby symbols...
    'ssl_verify_mode': ':verify_none',
    'log_level': ':info',
    # These are not symbols...
    'log_location': 'C:\\chef\\client.log',
    'validation_key': CHEF_VALIDATION_PEM_PATH,
    'client_key': "C:\\chef\\client.pem",
    'json_attribs': CHEF_FB_PATH,
    'file_cache_path': "C:\\chef\\cache",
    'file_backup_path': "C:\\chef\\backup",
    'show_time': True,
}
CHEF_RB_TPL_BOOL_KEYS = frozenset(['show_time'])
CHEF_RB_TPL_PATH_KEYS = frozenset([
    'log_location',
    'validation_key',
    'client_key',
    'file_cache_path',
    'json_attribs',
    'file_cache_path',
])
CHEF_RB_TPL_KEYS = list(CHEF_RB_TPL_DEFAULTS.keys())
CHEF_RB_TPL_KEYS.extend(CHEF_RB_TPL_BOOL_KEYS)
CHEF_RB_TPL_KEYS.extend(CHEF_RB_TPL_PATH_KEYS)
CHEF_RB_TPL_KEYS.extend([
    'server_url',
    'node_name',
    'environment',
    'validation_name',
])
CHEF_RB_TPL_KEYS = frozenset(CHEF_RB_TPL_KEYS)
# CHEF_RB_PATH = '/etc/chef/client.rb'
CHEF_RB_PATH = 'C:\\chef\\client.rb'
# CHEF_EXEC_PATH = '/usr/bin/chef-client'
CHEF_EXEC_PATH = 'C:\\opscode\\chef\\bin\\chef-client.bat'
CHEF_EXEC_DEF_ARGS = tuple(['-d', '-i', '1800', '-s', '20'])


def is_installed():
    if not os.path.isfile(CHEF_EXEC_PATH):
        return False
    if not os.access(CHEF_EXEC_PATH, os.X_OK):
        return False
    return True


def post_run_chef(chef_cfg):
    delete_pem = get_cfg_option_bool(chef_cfg,
                                     'delete_validation_post_exec',
                                     default=False)
    if delete_pem and os.path.isfile(CHEF_VALIDATION_PEM_PATH):
        os.unlink(CHEF_VALIDATION_PEM_PATH)


def get_template_params(instance_id, chef_cfg, log):
    params = CHEF_RB_TPL_DEFAULTS.copy()
    # Allow users to overwrite any of the keys they want (if they so choose),
    # when a value is None, then the value will be set to None and no boolean
    # or string version will be populated...
    for (k, v) in chef_cfg.items():
        if k not in CHEF_RB_TPL_KEYS:
            log.debug("Skipping unknown chef template key '%s'", k)
            continue
        if v is None:
            params[k] = None
        else:
            # This will make the value a boolean or string...
            if k in CHEF_RB_TPL_BOOL_KEYS:
                params[k] = get_cfg_option_bool(chef_cfg, k)
            else:
                params[k] = get_cfg_option_str(chef_cfg, k)
    # These ones are overwritten to be exact values...
    params.update({
        'generated_by': make_header(),
        'node_name': get_cfg_option_str(chef_cfg, 'node_name',
                                        default=instance_id),
        'environment': get_cfg_option_str(chef_cfg, 'environment',
                                          default='_default'),
        # These two are mandatory...
        'server_url': chef_cfg['server_url'],
        'validation_name': chef_cfg['validation_name'],
    })
    return params


def get_template_filename(name):
    fn = TEMPLATE_PATH_BASE % name
    if not os.path.isfile(fn):
        LOG.warn("No template found at %s for template named %s", fn, name)
        return None
    return fn


def handle(chef_cfg, log):
    """Handler method activated by cloud-init."""

    instance_id = get_cfg_option_str(chef_cfg, 'instance_id')

    # Ensure the chef directories we use exist
    chef_dirs = get_cfg_option_list(chef_cfg, 'directories')
    if not chef_dirs:
        chef_dirs = list(CHEF_DIRS)
    for d in itertools.chain(chef_dirs, REQUIRED_CHEF_DIRS):
        ensure_dir(d)

    # Set the validation key based on the presence of either 'validation_key'
    # or 'validation_cert'. In the case where both exist, 'validation_key'
    # takes precedence
    for key in ('validation_key', 'validation_cert'):
        if key in chef_cfg and chef_cfg[key]:
            write_file(CHEF_VALIDATION_PEM_PATH, chef_cfg[key])
            break

    # Create the chef config from template
    template_fn = get_template_filename('chef_client.rb')
    if template_fn:
        params = get_template_params(instance_id, chef_cfg, log)
        # Do a best effort attempt to ensure that the template values that
        # are associated with paths have there parent directory created
        # before they are used by the chef-client itself.
        param_paths = set()
        for (k, v) in params.items():
            if k in CHEF_RB_TPL_PATH_KEYS and v:
                param_paths.add(os.path.dirname(v))
        ensure_dirs(param_paths)
        templater.render_to_file(template_fn, CHEF_RB_PATH, params)
    else:
        log.warn("No template found, not rendering to %s",
                 CHEF_RB_PATH)

    # Set the first-boot json
    fb_filename = get_cfg_option_str(chef_cfg, 'firstboot_path',
                                     default=CHEF_FB_PATH)
    if not fb_filename:
        log.info("First boot path empty, not writing first boot json file")
    else:
        initial_json = {}
        if 'run_list' in chef_cfg:
            initial_json['run_list'] = chef_cfg['run_list']
        if 'initial_attributes' in chef_cfg:
            initial_attributes = chef_cfg['initial_attributes']
            for k in list(initial_attributes.keys()):
                initial_json[k] = initial_attributes[k]
        write_file(fb_filename, json.dumps(initial_json))

    # Try to install chef, if its not already installed...
    force_install = get_cfg_option_bool(chef_cfg,
                                        'force_install', default=False)
    if not is_installed() or force_install:
        run = install_chef(chef_cfg, log)
    elif is_installed():
        run = get_cfg_option_bool(chef_cfg, 'exec', default=True)
    else:
        run = False
    if run:
        run_chef(chef_cfg, log)
        post_run_chef(chef_cfg)


def run_chef(chef_cfg, log):
    log.debug('Running chef-client')
    cmd = [CHEF_EXEC_PATH]
    if 'exec_arguments' in chef_cfg:
        cmd_args = chef_cfg['exec_arguments']
        if isinstance(cmd_args, (list, tuple)):
            cmd.extend(cmd_args)
        elif isinstance(cmd_args, (str, basestring)):
            cmd.append(cmd_args)
        else:
            log.warn("Unknown type %s provided for chef"
                     " 'exec_arguments' expected list, tuple,"
                     " or string", type(cmd_args))
            cmd.extend(CHEF_EXEC_DEF_ARGS)
    else:
        cmd.extend(CHEF_EXEC_DEF_ARGS)
    subp(cmd, capture=False)


def install_chef(chef_cfg, log):
    url = get_cfg_option_str(chef_cfg, "msi_url", MSI_URL)
    retries = max(0, get_cfg_option_int(chef_cfg,
                                        "msi_url_retries",
                                        default=MSI_URL_RETRIES))
    response = url_helper.readurl(url=url, retries=retries)
    if not response.ok():
        log.warn("Could not download chef installer .msi from URL %s" % url)
        return False

    response = getattr(response, '_response', response)
    response.raw.decode_content = True
    with tempdir() as temp_dir:
        # Use tmpdir over tmpfile to avoid 'text file busy' on execute
        temp_file = "%s\\chef-windows.msi" % temp_dir
        write_file(temp_file, response.raw, mode=0700)
        subp(['msiexec', '/i', temp_file], capture=False)
    return True
