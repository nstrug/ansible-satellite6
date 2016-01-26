#!/usr/bin/env python

"""
Red Hat Satellite 6 external inventory script
=============================================

Ansible has a feature where instead of reading from /etc/ansible/hosts
as a text file, it can query external programs to obtain the list
of hosts, groups the hosts are in, and even variables to assign to each host.

To use this, copy this file over /etc/ansible/hosts and chmod +x the file.
This, more or less, allows you to keep one central database containing
info about all of your managed instances.

This script is an example of sourcing that data from Red Hat Satellite 6.
Each of the following satellite management entitities will correspond to a
group in Ansible:

* Location
* Lifecycle Environment
* Hostgroup
* Host Collection

See http://ansible.github.com/api.html for more info

Tested with Satellite 6.1.6

Changelog:
    - 2016-01-26 mburgerh: Cleanup
    - 2015-11-02 nstrug: Initial version, based on cobbler.py

"""

# (c) 2015, Nick Strugnell <nstrug@redhat.com>
#
# This file is part of Ansible,
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

######################################################################

import argparse
import ConfigParser
import os
import re
from time import time
import requests
import sys
import json

orderby_keyname = 'owners'  # alternatively 'mgmt_classes'


class SatelliteInventory(object):

    def __init__(self):

        """ Main execution path """
        self.conn = None

        self.inventory = dict()  # A list of groups and the hosts in that group
        self.cache = dict()  # Details about hosts in the inventory

        # Read settings and parse CLI arguments
        self.read_settings()
        self.parse_cli_args()

        self.post_headers = {'content-type': 'application/json'}
        self.ssl_verify = False

        self.org = self.get_json(self.sat_api + "organizations?search="
                                 + self._org_name)
        if self.org['results'] == []:
            sys.exit(1)

        if self.args.refresh_cache:
            self.update_cache()
        elif not self.is_cache_valid():
            self.update_cache()
        else:
            self.load_inventory_from_cache()
            self.load_cache_from_cache()

        data_to_print = ""

        # Data to print
        if self.args.host:
            data_to_print += self.get_host_info()
        else:
            data_to_print += self.json_format_dict(self.inventory, True)

        print(data_to_print)

    def get_json(self, url):
        r = requests.get(url, auth=(self._username, self._password),
                         verify=self.ssl_verify)
        return r.json()

    def is_cache_valid(self):
        """ Determines if cache files have expired or if it is still valid """

        if os.path.isfile(self.cache_path_cache):
            mod_time = os.path.getmtime(self.cache_path_cache)
            current_time = time()
            if (mod_time + self.cache_max_age) > current_time:
                if os.path.isfile(self.cache_path_inventory):
                    return True

        return False

    def read_settings(self):
        """ Reads the settings from the hammer.ini file """

        config = ConfigParser.SafeConfigParser()
        config.read(os.path.dirname(os.path.realpath(__file__))
                    + '/hammer.ini')

        self._host = config.get('hammer', 'host')
        self.sat_api = "%s/api/v2/" % self._host
        self.katello_api = "%s/katello/api/v2/" % self._host
        self._username = config.get('hammer', 'username')
        self._password = config.get('hammer', 'password')
        self._org_name = config.get('hammer', 'organisation')

        # Cache related
        cache_path = config.get('hammer', 'cache_path')
        self.cache_path_cache = cache_path + "/ansible-hammer.cache"
        self.cache_path_inventory = cache_path + "/ansible-hammer.index"
        self.cache_max_age = config.getint('hammer', 'cache_max_age')

    def parse_cli_args(self):
        """ Command line argument processing """

        parser = argparse.ArgumentParser(description='Produce an Ansible Inventory file based on Satellite 6')
        parser.add_argument('--list', action='store_true', default=True, help='List instances (default: True)')
        parser.add_argument('--host', action='store', help='Get all the variables about a specific instance')
        parser.add_argument('--refresh-cache', action='store_true', default=False,
                            help='Force refresh of cache by making API requests to hammer (default: False - use cache files)')
        self.args = parser.parse_args()

    def update_cache(self):
        """ Make calls to satellite and save the output in a cache """

        self.hostgroups = self.get_json(self.sat_api + "hostgroups")
        self.systems = self.get_json(self.sat_api + "hosts")

        for system in self.systems['results']:
            if system['hostgroup_name'] not in self.inventory:
                self.inventory[system['hostgroup_name']] = []
            self.inventory[system['hostgroup_name']].append(system['name'])

        self.write_to_cache(self.cache, self.cache_path_cache)
        self.write_to_cache(self.inventory, self.cache_path_inventory)

    def get_host_info(self):
        """ Get variables about a specific host """

        if not self.cache or len(self.cache) == 0:
            # Need to load index from cache
            self.load_cache_from_cache()

        if self.args.host not in self.cache:
            # try updating the cache
            self.update_cache()

            if self.args.host not in self.cache:
                # host might not exist anymore
                return self.json_format_dict({}, True)

        return self.json_format_dict(self.cache[self.args.host], True)

    def push(self, my_dict, key, element):
        """ Pushed an element onto an array that may not have been defined in
            the dict """

        if key in my_dict:
            my_dict[key].append(element)
        else:
            my_dict[key] = [element]

    def load_inventory_from_cache(self):
        """ Reads the index from the cache file sets self.index """

        cache = open(self.cache_path_inventory, 'r')
        json_inventory = cache.read()
        self.inventory = json.loads(json_inventory)

    def load_cache_from_cache(self):
        """ Reads the cache from the cache file sets self.cache """

        cache = open(self.cache_path_cache, 'r')
        json_cache = cache.read()
        self.cache = json.loads(json_cache)

    def write_to_cache(self, data, filename):
        """ Writes data in JSON format to a file """
        json_data = self.json_format_dict(data, True)
        cache = open(filename, 'w')
        cache.write(json_data)
        cache.close()

    def to_safe(self, word):
        """ Converts 'bad' characters in a string to underscores so they can be
            used as Ansible groups """

        return re.sub("[^A-Za-z0-9\-]", "_", word)

    def json_format_dict(self, data, pretty=False):
        """ Converts a dict to a JSON object and dumps it as a
            formatted string """

        if pretty:
            return json.dumps(data, sort_keys=True, indent=2)
        else:
            return json.dumps(data)

SatelliteInventory()
