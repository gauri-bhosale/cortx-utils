#!/usr/bin/env python3
#
# Copyright (c) 2021 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.

import os
import ldap
import glob
from shutil import copyfile
from cortx.utils.log import Log
from cortx.utils.conf_store import Conf
from setupReplication import Replication

class BaseConfig:
    Log.init('OpenldapProvisioning', '/var/log/cortx/utils/openldap', level='DEBUG')
    def add_attribute(binddn, dn, record, pwd):
        #add_s - init.ldif
        # Open a connection
        ldap_conn = ldap.initialize("ldapi:///")
        # Bind/authenticate with a user with apropriate rights to add objects
        ldap_conn.simple_bind_s(binddn, pwd)
        try:
            ldap_conn.add_s(dn, record)
        except Exception:
            Log.error('Error while adding attribute')
            raise Exception('Error while adding attribute')
        ldap_conn.unbind_s()

    def safe_remove(filename):
        try:
            os.remove(filename)
        except Exception:
            Log.error('Error while deleting ' + filename)

    def cleanup(forceclean):
        # Removing schemas
        filelist = glob.glob('/etc/openldap/slapd.d/cn=config/cn=schema/*ppolicy.ldif')
        for policyfile in filelist:
            BaseConfig.safe_remove(policyfile)
        module_files = ["cn=module{0}.ldif", "cn=module{1}.ldif", "cn=module{2}.ldif"]
        for module_file in module_files:
            module_file = '/etc/openldap/slapd.d/cn=config/'+ str(module_file)
            BaseConfig.safe_remove(module_file)
        mdb_directory = '/etc/openldap/slapd.d/cn=config/olcDatabase={2}mdb'
        try:
            files = glob.glob('/etc/openldap/slapd.d/cn=config/olcDatabase={2}mdb/*')
            for f in files:
                BaseConfig.safe_remove(f)
        except Exception:
            Log.error('Error while deleting '+ mdb_directory)
        mdbfile = '/etc/openldap/slapd.d/cn=config/olcDatabase={2}mdb.ldif'
        BaseConfig.safe_remove(mdbfile)
        #Data Cleanup
        if forceclean == 'True' :
            files = glob.glob('/var/lib/ldap/*')
            for f in files:
                BaseConfig.safe_remove(f)
        #Clear the password set in config
        conn = ldap.initialize("ldapi:///")
        conn.sasl_non_interactive_bind_s('EXTERNAL')
        Replication.deleteattribute(conn, "olcDatabase={0}config,cn=config", "olcRootPW")
        conn.unbind_s()

    def modify_attribute(dn, attribute, value):
        # Open a connection
        ldap_conn = ldap.initialize("ldapi:///")
        # Bind/authenticate with a user with apropriate rights to add objects
        ldap_conn.sasl_non_interactive_bind_s('EXTERNAL')
        mod_attrs = [(ldap.MOD_REPLACE, attribute, bytes(str(value), 'utf-8'))]
        try:
            ldap_conn.modify_s(dn, mod_attrs)
        except Exception:
            Log.error('Error while modifying attribute- '+ attribute)
            raise Exception('Error while modifying attribute' + attribute)
        ldap_conn.unbind_s()

    def perform_base_config(rootpassword, forcecleanup, config_values):
        forceclean = False
        ROOTDNPASSWORD = None
        ROOTDNPASSWORD = rootpassword
        if ROOTDNPASSWORD == None :
            Log.error('Password not provided for ldap configuration')
            quit()
        if forcecleanup != None :
            forceclean = forcecleanup
        mdb_dir = Conf.get(index= 'util_config_file_index', key='install_path') + '/cortx/utils/conf'
        BaseConfig.cleanup(forceclean)
        copyfile(mdb_dir + '/olcDatabase={2}mdb.ldif' ,\
        '/etc/openldap/slapd.d/cn=config/olcDatabase={2}mdb.ldif')
        os.system('chgrp ldap /etc/openldap/certs/password')
        cmd = 'slappasswd -s ' + str(ROOTDNPASSWORD)
        pwd = os.popen(cmd).read()
        pwd.replace('/','\/')
        #restart slapd post cleanup
        os.system('systemctl restart slapd')
        dn = 'olcDatabase={0}config,cn=config'
        BaseConfig.modify_attribute(dn, 'olcRootDN', 'cn=admin,cn=config')
        BaseConfig.modify_attribute(dn, 'olcRootPW', pwd)
        BaseConfig.modify_attribute(dn, 'olcAccess', '{0}to * by dn.base="gidNumber=0+uidNumber=0,cn=peercred,cn=external,cn=auth" write by self write by * read')
        dn = 'olcDatabase={2}mdb,cn=config'
        BaseConfig.modify_attribute(dn, 'olcSuffix', config_values.get('base_dn'))
        BaseConfig.modify_attribute(dn, 'olcRootDN', config_values.get('bind_base_dn'))
        ldap_conn = ldap.initialize("ldapi:///")
        ldap_conn.simple_bind_s(config_values.get('bind_base_dn'), ROOTDNPASSWORD)
        ldap_conn.sasl_non_interactive_bind_s('EXTERNAL')
        mod_attrs = [( ldap.MOD_ADD, 'olcDbMaxSize', [b'10737418240'] )]
        try:
            ldap_conn.modify_s(dn, mod_attrs)
        except Exception:
            Log.error('Error while modifying olcDbMaxSize attribute for olcDatabase={2}mdb')
            raise Exception('Error while modifying olcDbMaxSize attribute for olcDatabase={2}mdb')
        ldap_conn.unbind_s()
        BaseConfig.modify_attribute(dn, 'olcRootPW', pwd)
        BaseConfig.modify_attribute(dn, 'olcAccess', '{0}to attrs=userPassword by self write by dn.base="'+config_values.get('bind_base_dn')+'" write by anonymous auth by * none')
        BaseConfig.modify_attribute(dn, 'olcAccess', '{1}to * by dn.base="'+config_values.get('bind_base_dn')+'" write by self write by * none')

        #add_s - init.ldif
        add_record = [
         ('dc', [b'seagate'] ),
         ('o', [b'seagate'] ),
         ('description', [b'Root entry for seagate.com.']),
         ('objectClass', [b'top',b'dcObject',b'organization'])
        ]
        BaseConfig.add_attribute(config_values.get('bind_base_dn'), config_values.get('base_dn'), add_record, ROOTDNPASSWORD)

        #add iam constraint
        add_record = [
         ('cn', [b'module{0}'] ),
         ('olcModulePath', [b'/usr/lib64/openldap/'] ),
         ('olcModuleLoad', [b'unique.la'] ),
         ('objectClass', [b'olcModuleList'])
        ]
        BaseConfig.add_attribute("cn=admin,cn=config", "cn=module{0},cn=config", add_record, ROOTDNPASSWORD)

        add_record = [
         ('olcUniqueUri', [b'ldap:///?mail?sub?'] ),
         ('olcOverlay', [b'unique'] ),
         ('objectClass', [b'olcOverlayConfig',b'olcUniqueConfig'])
        ]
        BaseConfig.add_attribute("cn=admin,cn=config", "olcOverlay=unique,olcDatabase={2}mdb,cn=config", add_record, ROOTDNPASSWORD)

        add_record = [
('objectClass', [b'olcSchemaConfig']), ('cn', [b'ppolicy']), ('olcAttributeTypes', [b"{0}( 1.3.6.1.4.1.42.2.27.8.1.1 NAME 'pwdAttribute' EQUALITY objectIdentifierMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.38 )", b"{1}( 1.3.6.1.4.1.42.2.27.8.1.2 NAME 'pwdMinAge' EQUALITY integerMatch ORDERING integerOrderingMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{2}( 1.3.6.1.4.1.42.2.27.8.1.3 NAME 'pwdMaxAge' EQUALITY integerMatch ORDERING integerOrderingMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{3}( 1.3.6.1.4.1.42.2.27.8.1.4 NAME 'pwdInHistory' EQUALITY integerMatch ORDERING integerOrderingMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{4}( 1.3.6.1.4.1.42.2.27.8.1.5 NAME 'pwdCheckQuality' EQUALITY integerMatch ORDERING integerOrderingMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{5}( 1.3.6.1.4.1.42.2.27.8.1.6 NAME 'pwdMinLength' EQUALITY integerMatch ORDERING integerOrderingMatch  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{6}( 1.3.6.1.4.1.42.2.27.8.1.7 NAME 'pwdExpireWarning' EQUALITY integerMatch ORDERING integerOrderingMatch  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{7}( 1.3.6.1.4.1.42.2.27.8.1.8 NAME 'pwdGraceAuthNLimit' EQUALITY integerMatch ORDERING integerOrderingMatch  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{8}( 1.3.6.1.4.1.42.2.27.8.1.9 NAME 'pwdLockout' EQUALITY booleanMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.7 SINGLE-VALUE )", b"{9}( 1.3.6.1.4.1.42.2.27.8.1.10 NAME 'pwdLockoutDuration' EQUALITY integerMatch ORDERING integerOrderingMatch  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{10}( 1.3.6.1.4.1.42.2.27.8.1.11 NAME 'pwdMaxFailure' EQUALITY integerMatch ORDERING integerOrderingMatch  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{11}( 1.3.6.1.4.1.42.2.27.8.1.12 NAME 'pwdFailureCountInterval' EQUALITY integerMatch ORDERING integerOrderingMatch  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )", b"{12}( 1.3.6.1.4.1.42.2.27.8.1.13 NAME 'pwdMustChange' EQUALITY booleanMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.7 SINGLE-VALUE )", b"{13}( 1.3.6.1.4.1.42.2.27.8.1.14 NAME 'pwdAllowUserChange' EQUALITY booleanMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.7 SINGLE-VALUE )", b"{14}( 1.3.6.1.4.1.42.2.27.8.1.15 NAME 'pwdSafeModify' EQUALITY booleanMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.7 SINGLE-VALUE )", b'{15}( 1.3.6.1.4.1.4754.1.99.1 NAME \'pwdCheckModule\' DESC \'Loadable module that instantiates "check_password() function\' EQUALITY caseExactIA5Match SYNTAX 1.3.6.1.4.1.1466.115.121.1.26 SINGLE-VALUE )', b"{16}( 1.3.6.1.4.1.42.2.27.8.1.30 NAME 'pwdMaxRecordedFailure' EQUALITY integerMatch ORDERING integerOrderingMatch  SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )"]), ('olcObjectClasses', [b"{0}( 1.3.6.1.4.1.4754.2.99.1 NAME 'pwdPolicyChecker' SUP top AUXILIARY MAY pwdCheckModule )", b"{1}( 1.3.6.1.4.1.42.2.27.8.2.1 NAME 'pwdPolicy' SUP top AUXILIARY MUST pwdAttribute MAY ( pwdMinAge $ pwdMaxAge $ pwdInHistory $ pwdCheckQuality $ pwdMinLength $ pwdExpireWarning $ pwdGraceAuthNLimit $ pwdLockout $ pwdLockoutDuration $ pwdMaxFailure $ pwdFailureCountInterval $ pwdMustChange $ pwdAllowUserChange $ pwdSafeModify $ pwdMaxRecordedFailure ) )"])
]
        BaseConfig.add_attribute("cn=admin,cn=config", "cn=ppolicy,cn=schema,cn=config", add_record, ROOTDNPASSWORD)

        add_record = [
         ('cn', [b'module{1}'] ),
         ('olcModulePath', [b'/usr/lib64/openldap/'] ),
         ('olcModuleLoad', [b'ppolicy.la'] ),
         ('objectClass', [b'olcModuleList'])
        ]
        BaseConfig.add_attribute("cn=admin,cn=config", "cn=module{1},cn=config", add_record, ROOTDNPASSWORD)


        add_record = [
         ('objectClass', [b'olcOverlayConfig',b'olcPPolicyConfig']),
         ('olcOverlay',[b'ppolicy']),
         ('olcPPolicyDefault',[b'cn=passwordDefault,ou=Policies,dc=seagate,dc=com']),
         ('olcPPolicyHashCleartext',[b'FALSE']),
         ('olcPPolicyUseLockout',[b'FALSE']),
         ('olcPPolicyForwardUpdates',[b'FALSE'])
        ]
        BaseConfig.add_attribute("cn=admin,cn=config", "olcOverlay=ppolicy,olcDatabase={2}mdb,cn=config", add_record, ROOTDNPASSWORD)

        add_record = [
         ('objectClass', [b'organizationalUnit']),
         ('ou',[b'Policies'])
        ]
        BaseConfig.add_attribute("cn=admin,dc=seagate,dc=com", "ou=Policies,dc=seagate,dc=com", add_record, ROOTDNPASSWORD)

        add_record = [
         ('objectClass', [b'pwdPolicy',b'person',b'top']),
         ('cn',[b'passwordDefault']),
         ('sn',[b'passwordDefault']),
         ('pwdAttribute',[b'userPassword']),
         ('pwdReset',[b'TRUE']),
         ('pwdCheckQuality',[b'0']),
         ('pwdMinAge',[b'0']),
         ('pwdMaxAge',[b'0']),
         ('pwdMinLength',[b'0']),
         ('pwdInHistory',[b'0']),
         ('pwdMaxFailure',[b'0']),
         ('pwdFailureCountInterval',[b'0']),
         ('pwdLockout',[b'FALSE']),
         ('pwdLockoutDuration',[b'0']),
         ('pwdAllowUserChange',[b'TRUE']),
         ('pwdExpireWarning',[b'0']),
         ('pwdGraceAuthNLimit',[b'0']),
         ('pwdMustChange',[b'FALSE']),
         ('pwdSafeModify',[b'FALSE'])
        ]
        BaseConfig.add_attribute("cn=admin,dc=seagate,dc=com", "cn=passwordDefault,ou=Policies,dc=seagate,dc=com", add_record, ROOTDNPASSWORD)
