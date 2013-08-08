import os
import re
import math
import shutil
import libvirt
import ConfigParser

from Cheetah.Template import Template

from synapse.config import config
from synapse.logger import logger
from synapse.syncmd import exec_cmd
from synapse.resources.resources import ResourceException

import hyp_util

log = logger('hyp_libvirt')

HYPERVISORS_CONFIG_FILE = os.path.join(config.paths['config_path'],
                                       'plugins',
                                       'hypervisors.conf')

# Initialize the path to the template files
DOMAIN_TEMPLATE_FILE = hyp_util.get_config_option('general',
                                              'domain_template_file_path',
                                              HYPERVISORS_CONFIG_FILE)

DISK_TEMPLATE_FILE = hyp_util.get_config_option('general',
                                            'disk_template_file_path',
                                            HYPERVISORS_CONFIG_FILE)

PATH_TO_OS_FILES = '/tmp'
FLOPPY_MOUNTPOINT = '/mnt/floppy'

# The different types of hypervisors managed using libvirt
HYP_TYPE_KVM = 'kvm'
HYP_TYPE_XEN = 'xen'
HYP_TYPE_LXC = 'lxc'


def _get_readable_status(num_status):
    """
    Returns a readable standard status from a constant number of libvirt API.

    @param num_status: the libvirt status number of a virtual machine
    @type num_status: int
    """
    status = {libvirt.VIR_DOMAIN_NOSTATE: hyp_util.VM_STATE_UNKNOWN,
              libvirt.VIR_DOMAIN_RUNNING: hyp_util.VM_STATE_RUNNING,
              libvirt.VIR_DOMAIN_BLOCKED: hyp_util.VM_STATE_BLOCKED,
              libvirt.VIR_DOMAIN_PAUSED: hyp_util.VM_STATE_PAUSED,
              libvirt.VIR_DOMAIN_SHUTDOWN: hyp_util.VM_STATE_SHUTDOWN,
              libvirt.VIR_DOMAIN_SHUTOFF: hyp_util.VM_STATE_SHUTOFF,
              libvirt.VIR_DOMAIN_CRASHED: hyp_util.VM_STATE_CRASHED
             }[num_status]

    return status


def _connect(res_id):
    """
    Connects to libvirt.

    @param res_id: the hypervisor's id
    @type res_id: str
    """
    try:
        url = hyp_util.get_config_option(res_id, 'url',
                                         HYPERVISORS_CONFIG_FILE)
        return libvirt.open(url)
    except libvirt.libvirtError:
        return None


def _is_connected(connection):
    """
    Checks if the connection is still active.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance
    """
    try:
        connection.getInfo()
        return True
    except libvirt.libvirtError:
        connection = None
        return False


def _disconnect(connection):
    """
    Closes the connection.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance
    """
    connection.close()


def _get_VM(connection, attributes):
    """
    Retrieve the virtual machine with the given name.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        retrieve a virtual machine
    @type attributes: dict
    """
    try:
        vm = connection.lookupByName(attributes['name'])
    except libvirt.libvirtError as ex:
        raise ResourceException(ex)

    return vm


def _get_VMs(conn):
    """
    Returns all virtual machines for the given connection.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance
    """
    vms = []
    try:
        vms = [conn.lookupByID(x).name() for x in conn.listDomainsID()]
        defined_domains = conn.listDefinedDomains()
    except libvirt.libvirtError as err:
        raise ResourceException(err)

    return vms + defined_domains


def _create_VM(res_id, connection, dict_vm, dict_disk):
    """
    Creates a virtual machine and its disk storage and provisions the machine.

    @param res_id: the hypervisor's id
    @type res_id: str

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance
    """
    # Render the disk XML content from the template file
    tmpl_disk = Template(file=DISK_TEMPLATE_FILE, searchList=[dict_disk])
    disk_xml = tmpl_disk.respond()

    # Get the default storage pool
    pool = connection.storagePoolLookupByName('default')

    # Create the disk
    try:
        volume = pool.createXML(disk_xml, 0)
    except libvirt.libvirtError:
        raise ResourceException("The volume name already exists")

    if 'autounattend' in dict_vm and dict_vm['autounattend']:
        # Floppy path is used in the DOMAIN_TEMPLATE_FILE
        dict_vm['floppy'] = True
        dict_vm['floppy_path'] = _autounattend(dict_vm['autounattend'],
                                               dict_disk['storage_name'])
    else:
        dict_vm['floppy'] = False

    try:
        # Change some keys in the vm's dict
        dict_vm['memory'] = dict_vm['memory'] * 1024
        dict_vm['disk_path'] = volume.path()
        dict_vm['boot_dev'] = dict_vm['boot_dev']
        dict_vm['mode'] = 'create'

        # Render (pre-install) domain XML
        tmpl_domain = Template(file=DOMAIN_TEMPLATE_FILE, searchList=[dict_vm])
        domain_xml = tmpl_domain.respond()

        # Start the domain, in a non-persistent mode, using the XML
        prov_domain = connection.createLinux(domain_xml, 0)

        # Switch to define mode
        dict_vm['uuid'] = prov_domain.UUIDString()
        dict_vm['mode'] = 'define'

        # Render (post-install) domain XML
        tmpl_domain = Template(file=DOMAIN_TEMPLATE_FILE, searchList=[dict_vm])
        domain_xml = tmpl_domain.respond()

        # Persist the XML descriptor for post-install
        connection.defineXML(domain_xml)

    except libvirt.libvirtError as e:
        # Deletes the volume if it has been created
        try:
            name = dict_disk['storage_name'] + '.img'
            vol = pool.storageVolLookupByName(name)
            vol.delete(0)
        except libvirt.libvirtError:
            pass
        raise e

    return _get_status(connection, dict_vm)


def _autounattend(content, storage_name):
    total_size = 0
    dest = os.path.join(PATH_TO_OS_FILES, 'Autounattend.xml')
    log.debug('Creating Autounattend.xml')
    try:
        with open(dest, 'wb') as fd:
            fd.write(content)
    except IOError as err:
        raise ResourceException('Could not create floppy file (%s)' % err)

    name = 'floppy-' + storage_name + '.img'
    tmp_floppy_path = os.path.join(PATH_TO_OS_FILES, name)
    log.debug("Temporary floppy path: %s" % tmp_floppy_path)

    # Convert bytes to kilobytes and add some space to filesystem header
    total_size = total_size / 1024 + 1044

    # Create floppy image
    log.debug('Creating floppy image of size [%s]' % total_size)
    hyp_util.create_fs(tmp_floppy_path, total_size)

    # Create mount point
    try:
        os.mkdir(FLOPPY_MOUNTPOINT)
    except OSError:
        pass

    # Mount floppy image
    log.debug("Mounting floppy image on [%s]" % FLOPPY_MOUNTPOINT)
    cmd = ['mount', tmp_floppy_path, FLOPPY_MOUNTPOINT]
    ret = exec_cmd(' '.join(cmd))
    if ret['returncode'] != 0:
        raise ResourceException(ret['stderr'])

    # Copy the file on the mounted floppy.
    log.debug("Copying files on floppy")
    try:
        shutil.copy(dest, FLOPPY_MOUNTPOINT)
    except (IOError, shutil.Error) as ex:
        raise ResourceException("Error when copying floppy files: %s" %
                                str(ex))

    # Unmounts floppy image
    log.debug("Unmounting floppy")
    cmd = ['umount', FLOPPY_MOUNTPOINT]
    ret = exec_cmd(' '.join(cmd))
    if ret['returncode'] != 0:
        raise ResourceException(ret['stderr'])

    # Initializes final path to floppy image
    final_floppy_path = os.path.join('/var/lib/libvirt/images', name)

    # Copies floppy image to libvirt images directory
    log.debug("Copying floppy image to libvirt storage pool (%s)" %
              final_floppy_path)
    try:
        shutil.copyfile(tmp_floppy_path, final_floppy_path)
    except (IOError, shutil.Error) as ex:
        raise ResourceException("Error when copying floppy image to libvirt "
                                "images directory: " + str(ex))

    # Cleanups all unused files and directories
    try:
        os.remove(tmp_floppy_path)
        os.rmdir(FLOPPY_MOUNTPOINT)
    except OSError as ex:
        raise ResourceException("Error when removing "
                                "files and directories: " + str(ex))

    return final_floppy_path


def _delete_VM(connection, attributes):
    """
    Deletes a VM and even its disk volume if specified in attributes.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        delete a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    # If the attribute 'delete_volumes' is specified
    if ('delete_volumes' in attributes and
        attributes['delete_volumes'] == True):
            # Retrieve all volumes paths
            volume_paths = re.findall("<source file='(.*?)'/>", vm.XMLDesc(1))

            for volume_path in volume_paths:
                try:
                    # Delete each volume
                    volume = connection.storageVolLookupByPath(volume_path)
                    volume.delete(0)
                # If the volume is not defined in libvirt
                except libvirt.libvirtError:
                    try:
                        # Delete the file on the filesystem
                        os.remove(volume_path)
                    except OSError:
                        pass

    # Shutdown the virtual machine
    if vm.isActive():
        vm.destroy()

    # Delete the virtual machine
    vm.undefine()

    return _get_status(connection, attributes)


def _exists(connection, attributes):
    """
    Checks if a VM exists. Otherwise, raises an exception.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        check the existence of a virtual machine
    @type attributes: dict
    """
    try:
        _get_VM(connection, attributes)
    except ResourceException:
        return False

    return True


def _start(connection, attributes):
    """
    Starts a VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        start a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if vm.isActive() != 1:
        vm.create()

    else:
        raise ResourceException("The VM is already running")

    return _get_status(connection, attributes)


def _shutdown(connection, attributes):
    """
    Shuts down a VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        shutdown a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if vm.isActive() == 1:
        vm.shutdown()

    else:
        raise ResourceException("The VM is not running")

    return _get_status(connection, attributes)


def _shutoff(connection, attributes):
    """
    Shuts off a VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        shutoff a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if vm.isActive() == 1:
        vm.destroy()

    else:
        raise ResourceException("The VM is not running")

    return _get_status(connection, attributes)


def _reboot(connection, attributes):
    """
    Reboots a VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        reboot a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if vm.isActive() == 1:
        vm.reboot(0)

    else:
        raise ResourceException("The VM is not running")

    return _get_status(connection, attributes)


def _pause(connection, attributes):
    """
    Pauses a VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        pause a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if vm.isActive():
        vm.suspend()

    else:
        raise ResourceException("The VM must be running")

    return _get_status(connection, attributes)


def _resume(connection, attributes):
    """
    Resumes a paused VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        resume a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if _get_status(connection, attributes) == libvirt.VIR_DOMAIN_PAUSED:
        vm.resume()

    else:
        raise ResourceException("The VM is not paused")

    return _get_status(connection, attributes)


def _get_disk_path(connection, storage_name):
    """
    Returns the path to the disk volume.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param storage_name: The storage name
    @type attributes: string
    """
    pool = connection.storagePoolLookupByName('default')

    try:
        volume = pool.storageVolLookupByName(storage_name)
    except libvirt.libvirtError:
        raise ResourceException("The given storage name is unknown")

    path = volume.path()

    return path


def _get_status(connection, attributes):
    """
    Returns the status code of a specified VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        retrieve the status of a virtual machine
    @type attributes: dict
    """
    try:
        vm = _get_VM(connection, attributes)
        return vm.info()[0]
    except (ResourceException, libvirt.libvirtError):
        return 0


def _get_disk_size(connection, attributes):
    """
    Returns the size and unit of a disk image using the qemu-img command.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        retrieve the disk size of a virtual machine
    @type attributes: dict
    """
    pool = connection.storagePoolLookupByName('default')

    try:
        volume = pool.storageVolLookupByName(attributes['storage_name'] + \
                                             '.img')
    except libvirt.libvirtError:
        raise ResourceException("The given storage name is unknown")

    return volume.info()[1]


def _get_memory(connection, attributes):
    """
    Returns the current memory of a specified VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        get the memory size of a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)
    mem_size = vm.info()[1]

    return mem_size


def _set_memory(connection, attributes):
    """
    Sets the memory of a virtual machine.
    The VM must be shutdown to execute this method.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        set the memory size of a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if vm.isActive() == True:
        raise ResourceException("The VM needs to shutdown to resize the "
                                "memory")

    try:
        memory = int(attributes['memory']) * 1000
        vm.setMemoryFlags(memory, libvirt.VIR_DOMAIN_MEM_MAXIMUM)
        vm.setMemoryFlags(memory, libvirt.VIR_DOMAIN_AFFECT_CONFIG)
    except (TypeError, ValueError):
        raise ResourceException("The given memory size is not a integer")

    return _get_memory(connection, attributes)


def _get_vcpus(connection, attributes):
    """
    Returns the number of CPUs.
    The VM must be running to retrieve it.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        get the number of CPU of a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if not vm.isActive():
        raise ResourceException("The CPUs infos can't be retrieved while the "
                                "VM is not running")

    num_vcpus = vm.maxVcpus()

    return num_vcpus


def _set_vcpus(connection, attributes):
    """
    Sets the number of CPUs.
    The VM must be shut down to change this setting.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        set the number of CPU of a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)

    if vm.isActive():
        raise ResourceException("The VM must be shutdown before updating the "
                                "number of CPUs")

    try:
        num_cpu = int(attributes['num_cpu'])
        vm.setVcpusFlags(num_cpu, libvirt.VIR_DOMAIN_VCPU_MAXIMUM)
        vm.setVcpusFlags(num_cpu, libvirt.VIR_DOMAIN_VCPU_CONFIG)
    except (TypeError, ValueError):
        raise ResourceException("The given number of CPU is not a integer")

    return attributes['num_cpu']


def _get_vnc_port(connection, attributes):
    """
    Returns the VNC port of a specified VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        set the VNC port of a virtual machine
    @type attributes: dict
    """
    vm = _get_VM(connection, attributes)
    matches = re.search("type='vnc' port='(\\d{4,5})'", vm.XMLDesc(1))

    if matches is None:
        return -1
    else:
        return matches.groups()[0]


def _get_vnc_hostname(connection):
    """
    Returns the VNC hostname of a specified VM.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    """
    return connection.getHostname()


def _set_disk_size(connection, attributes):
    """
    Resize a disk image
    The following lines are from the man of qemu-img.

    Before using this command to shrink a disk image, you MUST use file
    system and partitioning tools inside the VM to reduce allocated file
    systems and partition sizes accordingly.  Failure to do so will
    result in data loss!

    After using this command to grow a disk image, you must use file
    system and partitioning tools inside the VM to actually begin using
    the new space on the device.

    @param connection: a connection to libvirt
    @type connection: libvirt.virConnect instance

    @param attributes: the dictionary of the attributes that will be used to
                        set the disk size of a virtual machine
    @type attributes: dict
    """
    # Get bytes out of both sizes
    old_size = _get_disk_size(connection, attributes)
    new_size = hyp_util.convert_size_to_bytes(attributes['disk_size'],
                                              attributes['disk_size_unit'])

    # Get the sign of the operation
    if old_size < new_size:
        sign = '+'
    else:
        sign = '-'

    # Get the amount that we'll add or remove from the actual size
    diff_size = math.fabs(old_size - new_size)

    if diff_size != 0:
        storage_name = attributes['storage_name'] + '.img'
        # Build the command that will resize the disk image
        cmd = []
        cmd.append('/usr/bin/qemu-img')
        cmd.append('resize')
        cmd.append(_get_disk_path(connection, storage_name))
        cmd.append(sign + str(diff_size))

        ret = exec_cmd(' '.join(cmd))
        if ret['returncode'] != 0:
            raise ResourceException(ret['stderr'])

    # Return the new disk size
    return _get_disk_size(connection, attributes)


def _init_hypervisor_attributes(res_id, attributes):
    """
    Initializes attributes depending on hypervisor type.

    @param res_id: the hypervisor's id
    @type res_id: str

    @param attributes: the dictionary of the attributes that will be used to
                        set the memory size of a virtual machine
    @type attributes: dict
    """
    hypervisor_type = hyp_util.get_config_option(res_id, 'hyp_type',
                                                 HYPERVISORS_CONFIG_FILE)

    # KVM hypervisor
    if hypervisor_type == HYP_TYPE_KVM:
        if 'os_type' not in attributes:
            attributes['os_type'] = 'hvm'

        if 'disk_driver' not in attributes:
            attributes['disk_driver'] = 'qemu'

        if 'disk_type' not in attributes:
            attributes['disk_type'] = 'raw'

    # XEN hypervisor
    elif hypervisor_type == HYP_TYPE_XEN:
        if 'os_type' not in attributes:
            attributes['os_type'] = 'linux'

        if 'disk_driver' not in attributes:
            attributes['disk_driver'] = 'tap'

        if 'disk_type' not in attributes:
            attributes['disk_type'] = 'raw'

    # LXC hypervisor
    elif hypervisor_type == HYP_TYPE_LXC:
        if 'os_type' not in attributes:
            attributes['os_type'] = 'exe'

    else:
        raise ResourceException("Unknown hypervisor type '%s'" %
                                hypervisor_type)

    if 'emulator_path' not in attributes:
        try:
            attributes['emulator_path'] = hyp_util.get_config_option(
                                            res_id, 'emulator_path',
                                            HYPERVISORS_CONFIG_FILE)
        except ConfigParser.NoOptionError:
            raise ResourceException("Emulator path not found in "
                                    "hypervisors configuration file")
