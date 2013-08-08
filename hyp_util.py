"""
Created on 18 avr. 2012

@author: pierre-yves
"""
import os
import shutil
import uuid
import urllib
import urllib2
import ConfigParser

from urlparse import urlparse

from synapse.logger import logger
from synapse.syncmd import exec_cmd
from synapse.resources.resources import ResourceException

log = logger('hyp_util')

# The different states of a virtual machine
VM_STATE_UNKNOWN = 'unknown'
VM_STATE_RUNNING = 'running'
VM_STATE_BLOCKED = 'blocked'
VM_STATE_PAUSED = 'paused'
VM_STATE_SHUTDOWN = 'shutdown'
VM_STATE_SHUTOFF = 'shutoff'
VM_STATE_CRASHED = 'crashed'
VM_STATE_REBOOTING = 'rebooting'


def convert_size_to_bytes(size, unit):
    """
    Converts the size of a specified unit into bytes.

    @param size: the size to convert
    @type size: int

    @param unit: the unit of the given size
    @type unit: str
    """
    # Convert kilobytes to bytes
    if unit == 'k' or unit == 'K':
        b = size * 2 ** 10
    # Convert megabytes to bytes
    elif unit == 'M':
        b = size * 2 ** 20
    # Convert gigabytes to bytes
    elif unit == 'G':
        b = size * 2 ** 30
    # Convert terabytes to bytes
    elif unit == 'T':
        b = size * 2 ** 40

    return b


def get_file_from_content(uri, dest_dir, custom_name=None):
    """
    Get a file from URL, base64 string or local path and copy it to
    dest path.

    A file is a dict with the following keys : name, content_type
    and content

    @param uri
    @type uri: str

    @param dest_dir: the destination directory in which the file should be
                        after the operations
    @type dest_dir: str
    """
    parsed = urlparse(uri)
    path = parsed.path
    size = 0
    # If the content type is an URL
    if parsed.scheme == 'http':
        try:
            # Download the file
            tmp_file = download_file_from_url(uri, dest_dir,
                                              file_name=custom_name)
            # Retrieve its size
            size = os.path.getsize(tmp_file)
        except OSError as e:
            raise ResourceException(str(e))

    # If the content type is a path on the current filesystem
    elif parsed.scheme == 'file':
        # If the path points to a file, then retrieve its size and copy it to
        # the destination directory
        if os.path.isfile(path):
            size = os.path.getsize(path)
            filename = custom_name or path.split(os.sep)[-1]
            tmp_file = os.path.join(dest_dir, filename)
            shutil.copyfile(path, tmp_file)
        else:
            raise ResourceException("The file '%s' does not exist." % parsed)

    return size


def dl_file(url, dest):
    size = 0
    file_name = url.split(os.path.sep)[-1]
    dest = os.path.join(dest, file_name)
    dled = urllib2.urlopen(url)
    output = open(dest, 'wb')
    output.write(dled.read())
    output.close()
    if os.path.isfile(dest):
        size = os.path.getsize(dest)
    return dest, size


def get_bool(value):
    if isinstance(value, basestring):
        return value.lower() in ["true", "yes", "y"]
    elif isinstance(value, bool):
        return value


def generate_uuid(upper=True):
    """
    generates a universal unique identifier

    @param upper: defines if the generated uuid should be in upper case
                    or not
    @type upper: bool
    """
    return uuid.uuid1().get_hex().upper() if upper else uuid.uuid1().get_hex()


def download_file_from_url(url, destination_path, file_name=None):
    """
    Downloads a file from URL and write it to the specified destination
    path.

    @param url: the url that points to a file
    @type url: str

    @param destination_path: the path to the destination directory in which the
                                file will be downloaded
    @type destination_path: str

    @param file_name: the name of the file after download
    @type file_name: str
    """
    if file_name is None:
        file_name = url.split(os.path.sep)[-1]

    log.info("Download started (%s)" % url.split(os.path.sep)[-1])

    # Retrieve the url stream
    try:
        url_stream = urllib.urlopen(url)
    except ValueError, ex:
        raise ResourceException(ex)

    # Create and open the destination file
    f = open(os.path.join(destination_path, file_name), 'wb')

    cur_decade = 0
    percent = 0
    block_sz = 8192
    downloaded_size = 0
    # Retrieve the size of the file to download
    full_size = url_stream.info().get('Content-Length')

    log.debug("Download progress (%s) : %d%%" %
              (url.split(os.path.sep)[-1], cur_decade * 10))

    # Download the file block per block
    while True:
        buf = url_stream.read(block_sz)

        downloaded_size += len(buf)
        percent = 1 - ((int(full_size) - downloaded_size) / float(full_size))

        # Display a message in the log at each decade
        if cur_decade != int(percent * 10):
            cur_decade = int(percent * 10)
            log.debug("Download progress (%s) : %d%%" %
                      (url.split(os.path.sep)[-1], cur_decade * 10))

        if not buf:
            break

        # Write the block in the file
        f.write(buf)

    log.info("Download ended (%s)" % url.split(os.path.sep)[-1])

    return os.path.join(destination_path, file_name)


def get_dir_size(start_path):
    """
    Returns the total size of the content of a directory.

    @param start_path: the path to the directory to retrive the size
    @type start_path: str
    """
    total_size = 0

    for dirpath, _, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)

    return total_size


def create_fs(path, size, fstype='vfat'):
    """
    Create a filesystem image.

    @param path: path to image
    @type path: str

    @param size: image size in bytes
    @type size: long

    @param fstype: type of the filesystem
    @type size: str
    """
    cmd = []
    cmd.append('mkfs.' + fstype)
    cmd.append('-C')
    cmd.append(path)
    cmd.append(str(size))

    ret = exec_cmd(' '.join(cmd))
    if ret['returncode'] != 0:
        raise ResourceException(ret['stderr'])


def read_config_file(file_name):
    """
    Returns a parsed configuration file.

    @param file_name: the path to the configuration file
    @type file_name: str
    """
    config = ConfigParser.ConfigParser()

    try:
        ret = config.read(file_name)
        if not ret:
            raise ResourceException("The configuration file '%s' doesn't exist"
                                    % file_name)
    except ConfigParser.MissingSectionHeaderError:
        raise ResourceException("Couldn't parse configuration file '%s'" %
                                file_name)

    return config


def get_config_option(res_id, option, config_path):
    """
    Retrieves an option in a configuration file.

    @param res_id: the hypervisor's id corresponding to a section in the
                    configuration file
    @type res_id: str

    @param option: the option to retrieve the value
    @type option: str

    @param config_path: the path to the configuration file
    @type config_path: str
    """
    # Retrive the configuration file
    config = read_config_file(config_path)

    # If the section exists in the configuration file
    if config.has_section(res_id):
        try:
            # Return the value of the given option
            return config.get(res_id, option)
        except ConfigParser.NoOptionError:
            raise ResourceException("The option '%s' doesn't exist in "
                                    "libvirt configuration file." % option)
    else:
        raise ResourceException("The hypervisor '%s' doesn't exist in the "
                                "configuration file." % res_id)


def create_pxe_config_file(mac_address, kernel_path, initrd_path,
                           kernel_params, config_filename):
    """
    Create the configuration file for a PXE boot

    @param mac_address: the MAC address of the machine
    @type mac_address: str

    @param kernel_path: the path to the vmlinuz file
    @type kernel_path: str

    @param initrd_path: the path to the initrd.img file
    @type initrd_path: str

    @param kernel_params: the parameters to pass to the kernel
    @type kernel_params: str

    @param config_filename: the path to the configuration file
    @type config_filename: str
    """
    # Initialize the file name
    filename = '01-' + mac_address.replace(':', '-')

    # Retrieve the TFTP path
    tftp_path = get_config_option('general', 'tftp_path', config_filename)

    # Create the configuration file and write its content
    f = open(os.path.join(tftp_path, "pxelinux.cfg", filename), "w")
    lines = ["default linux\n",
             "prompt 0\n",
             "timeout 1\n",
             "label linux\n",
             "    kernel %s\n" % kernel_path,
             "    append initrd=%s %s\n" % (initrd_path, kernel_params)]
    f.writelines(lines)
    f.close()
