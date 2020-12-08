#!/bin/python3

# CORTX Python common library.
# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.

import os, errno, inspect
from urllib.parse import urlparse

from cortx.utils.kv_store import kv_store_collection
from cortx.utils.kv_store.error import KvError

class KvStoreFactory:
    """ Factory class for File based KV Store """

    _stores = {}

    @staticmethod
    def get_instance(store_url):
        """ Obtain instance of KvStore for given file_type """

        url_spec = urlparse(store_url)
        store_type = url_spec.scheme
        store_loc = url_spec.netloc
        store_path = url_spec.path

        if store_type in KvStoreFactory._stores.keys():
            return KvStoreFactory._stores[store_type]

        storage = inspect.getmembers(kv_store_collection, inspect.isclass)

        for name, cls in storage:
            if store_type == cls.name:
                KvStoreFactory._stores[store_type] = \
                    cls(store_loc, store_path)
                return KvStoreFactory._stores[store_type]

        raise KvStoreError(errno.EINVAL, "Invalid store type %s", \
            store_type)

class KvStore:
    """ Abstraction over all kinds of KV based Storage """

    def __init__(self, store_loc, store_path):
        self._store_loc = store_loc
        self._store_path = store_path

    @property
    def path(self):
        return self._store_path

    @property
    def loc(self):
        return self._store_loc

    def _get(self, key, data: dict) -> str:
        """ Obtain value for the given key """
        k = key.split('.', 1)
        if k[0] not in data.keys(): return None
        return self._get(k[1], data[k[0]]) if len(k) > 1 else data[k[0]]

    def get(self, keys: list) -> list:
        """ Obtains values of keys. Return list of values. """
        data = self.load()
        vals = []
        for key in keys:
            val = self._get(key, data)
            vals.append(val)
        return vals

    def _set(self, key: str, val: str, data: dict):
        k = key.split('.', 1)
        if len(k) == 1:
            data[k[0]] = val
            return
        if k[0] not in data.keys():
            data[k[0]] = {}
        self._set(k[1], val, data[k[0]])

    def set(self, keys: list, vals: list):
        """ Updates a given set of keys and values """
        if len(keys) != len(vals):
            raise KvError(errno.EINVAL, "Mismatched keys & values %s:%s",\
                keys, vals)
        data = self.load()
        for key, val in zip(keys, vals):
            self._set(key, val, data)
        self.dump(data)

    def _delete(self, key: str, data: dict):
        k = key.split('.', 1)
        if len(k) == 1:
            del data[k[0]]
            return
        if k[0] not in data.keys():
            return
        self._delete(k[1], data[k[0]])
        

    def delete(self, keys: list):
        """ Deletes given set of keys from the """
        data = self.load()
        for key in keys:
            self._delete(key, data)
        self.dump(data)

    def load(self):
        """ Loads and returns data from KV storage """
        raise KvError(errno.ENOSYS, "%s:load() not implemented", \
            type(self).__name__)

    def dump(self, data):
        """ Dumps data onto the KV Storage """
        raise KvError(errno.ENOSYS, "%s:dump() not implemented", \
            type(self).__name__)


# TODO: Test Code - To be removed
if __name__ == "__main__":
    import sys

    kv_store = KvStoreFactory.get_instance(sys.argv[1])
    data = kv_store.load()
    print(data)

    if len(sys.argv) > 2:
        cmd = sys.argv[2]
        if cmd == 'get':
            key = sys.argv[3]
            print(kv_store.get([key]))

        elif cmd == 'set':
            key = sys.argv[3]
            val = sys.argv[4]
            kv_store.set([key], [val])
            data = kv_store.load()
            print(data)

        elif cmd == 'delete':
            key = sys.argv[3]
            kv_store.delete([key])                        
            data = kv_store.load()
            print(data)