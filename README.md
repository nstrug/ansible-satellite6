Ansible Dynamic Inventory for Red Hat Satellite 6
=================================================
* Author: Nick Strugnell
* Email: nstrug@redhat.com
* Date: 2015-12-02
* Version: 0.1.0

### Introduction
This is a dynamic inventory script to drive Ansible from Red Hat Satellite 6. It's based on the Cobbler inventory script [here](https://github.com/ansible/ansible/blob/devel/contrib/inventory/cobbler.py)
It uses the same caching mechanism as that script so you might want to refer to that to understand it a little better.

Currently, hosts are grouped by hostgroups only. I will add functionality to group by host collection, lifecycle environment, location, organisation etc.

### Usage
Copy satellite-inventory.py and hammer.ini to /etc/ansible and ensure that satellite-inventory.py is executable.
Put your satellite credentials in the hammer.ini file.

You should then be able to run ansible against hostgroups e.g.:
ansible <my_hostgroup> -i /etc/ansible/satellite-inventory.py -m setup


