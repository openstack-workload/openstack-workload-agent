#!/usr/bin/python

import json
import psutil
import pprint
from operator import itemgetter 
import os.path
import time
import bytes2human
import xml.etree.ElementTree as ET
#from lxml import etree
import multiprocessing
import stackconfig
import socket
import datetime
import redis
import sys

r = redis.Redis(
    host=           stackconfig.REDIS_SERVER,
    port=           stackconfig.REDIS_PORT, 
    password=       stackconfig.REDIS_PASSWORD
)


DBDIR                       = "/opt/stackwithless/agent/var/"
LIBVIRTDIR                  = "/etc/libvirt/qemu/"
DBFILE                      = DBDIR + "/last.json"
NAMESPACE                   = "{http://openstack.org/xmlns/libvirt/nova/1.0}"

firsttime                   = True
kvm_procs                   = {}
sys_info                    = {}
meta_info                   = {}

epoch_time                  = time.time()
minutes_since_boot          = (epoch_time - psutil.boot_time()) / 60 
meta_info['db_time']        = None
meta_info['hostname']       = socket.gethostname()

now = datetime.datetime.now()
meta_info['minuteofday']    = now.hour * 60 + now.minute


epoch_db_last               = r.hget('hosts.db_time', meta_info['hostname'])
sys_info['boot_time']       = psutil.boot_time()


r.hset('hosts.db_time',     meta_info['hostname'], epoch_time)
r.hset('hosts.lastminute',  meta_info['hostname'], meta_info['minuteofday'])


jloads                      = None

key_json = 'hosts.json.' + meta_info['hostname']


if epoch_db_last == None or minutes_since_boot < 10:
    firsttime               = True
    print epoch_db_last, minutes_since_boot


else:

    json_last                    = r.hget(key_json, str(int(meta_info['minuteofday']) - 1))
    if json_last != None:
        firsttime               = False
        jloads                  = json.loads(json_last)
        #pprint.pprint(jloads)
        print("hget found", key_json, str(int(meta_info['minuteofday']) - 1))
   
    #epoch_dbfile = os.path.getmtime(DBFILE)
    epoch_diff              = epoch_time - float(epoch_db_last)


meta_info['firsttime']              = firsttime
meta_info['minutes_since_boot']     = minutes_since_boot
meta_info['epoch_time']             = epoch_time



virtual_memory                  = psutil.virtual_memory()
sys_info['ram_total']           = virtual_memory.total
sys_info['ram_available']       = virtual_memory.available
sys_info['ram_used']            = virtual_memory.used
sys_info['ram_free']            = virtual_memory.free
sys_info['ram_buffers']         = virtual_memory.buffers
sys_info['ram_cached']          = virtual_memory.cached
sys_info['ram_shared']          = virtual_memory.shared
sys_info['cpu_percent']         = psutil.cpu_percent(interval=1)
sys_info['cores']               = multiprocessing.cpu_count()
swap                            = psutil.swap_memory()
sys_info['ram_swap']            = swap.total


def namespace_add(s):
    return NAMESPACE + s

def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]

def namespace_del(s):
    return remove_prefix(s, NAMESPACE)


# Iterate over all running process
for proc in psutil.process_iter():
    try:
        pname = proc.name()

        if pname == "qemu-kvm":
            pid =           proc.pid
            cputime =       proc.cpu_times()
            memory =        proc.memory_info()
            memory_vms =    memory.vms
            cmdline =       proc.cmdline()
            cmdline2 =      cmdline[2]
            cmdline3 =      cmdline2.split(',')
            cmdline4 =      cmdline3[0].split('=')
            instance =      cmdline4[1]
            cputime_sum =   sum(cputime)

            cputime_diff =  None
            pid_unicode =   unicode(pid)
            cputime_vcpu =  None

            # if not first time
            if jloads != None and pid_unicode in jloads:
               cputime_diff         = float(cputime_sum) - float(jloads[pid_unicode]['cputime'])
               cputime_vcpu         = float(cputime_diff / epoch_diff)

                

            proc_info = {
                'pid':              pid,
                'name':             pname,
                'cputime':          sum(cputime),
                'memory':           memory_vms,
                'memory_formated':  bytes2human.bytes2human(memory_vms),
                'instance':         instance,
                'cputime_diff':     cputime_diff,
                'cputime_vcpu':     cputime_vcpu,
            }

            #print(proc_info)

            kvm_procs[pid] = proc_info


    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass



# Interate over all libvirt vms
for pid in kvm_procs:
    libvirtdata = {}

    libvirtfile = LIBVIRTDIR + str(kvm_procs[pid]['instance']) + ".xml"

    if os.path.exists(libvirtfile):
        tree = ET.parse(libvirtfile)

        root = tree.getroot()
    
        for el in root.iter('uuid'):
            libvirtdata['uuid'] = el.text
            for el2 in el:
                print(el2)

        for el in root:
            if el.tag == "metadata":
                for el2 in el:
                    if el2.tag == namespace_add("instance"):
                        for el3 in el2:
                            tag = namespace_del(el3.tag)
                            if tag == "flavor":
                                if "name" in el3.attrib:
                                    flavor_name = el3.attrib["name"].strip()
                                    libvirtdata['flavor_name'] = flavor_name
                                for el4 in el3:
                                    tag = namespace_del(el4.tag)
                                    libvirtdata[tag] = el4.text
                            elif tag == "owner":
                                for el4 in el3:
                                    tag = namespace_del(el4.tag)

                                    if "uuid" in el4.attrib:
                                        uuid = el4.attrib["uuid"]
                                        libvirtdata[tag] = uuid

        #for el2 in tree.findall("metadata"):
        #    print(el2.text)

        #tree = etree.parse(libvirtfile)
        #root = etree.Element("uuid")
        #for element in root.iter():
        #    print("%s - %s" % (element.tag, element.text)) 

    #print(libvirtdata)



json_data = {'sys_info': sys_info, 'meta_info': meta_info, 'kvm_procs': kvm_procs}



#newlist = kvm_procs(key=operator.itemgetter('cputime'))
#newlist = kvm_procs.sort(lambda x,y : cmp(x['cputime'], y['pid']))
#kvm_procs = sorted(kvm_procs, key=itemgetter('cputime')) 

#pprint.pprint(kvm_procs)

# save to dbfile

json_dumps = json.dumps(json_data)
r.hset(key_json, meta_info['minuteofday'], json_dumps)



#json_save = open(DBFILE, "w")
#json_save.write(json_dumps)
#json_save.close()

