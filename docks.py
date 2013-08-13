import os
import ConfigParser

import docker

from synapse.resources.resources import ResourceException
from synapse.config import config
from synapse.logger import logger
from synapse.resources.resources import ResourcesController
from synapse.task import OutgoingMessage, AmqpTask


@logger
class DocksController(ResourcesController):
    __resource__ = 'docks'

    # The configuration file of the docks plugin
    DOCKS_CONFIG_FILE = os.path.join(config.paths['config_path'],
                                     'plugins', 'docks.conf')

    def __init__(self, mod):
        super(DocksController, self).__init__(mod)

        # Loads the configuration file.
        self.config = self._load_config_file()

        # For each dock, create the Docker client.
        self.docks = {}
        for key, value in self.config.iteritems():
            self.docks[key] = docker.Client(base_url=value['url'],
                                            version='1.3')

    def read(self, res_id=None, attributes=None):
        """
        """
        status = {}

        if res_id is None or res_id == '':
            status['docks'] = self.config.keys()
        elif res_id in self.docks:
            try:
                client = self.docks[res_id]
                if attributes.get('container'):
                    status = client.inspect_container(attributes['container'])
                else:
                    status = client.containers()
            except Exception as e:
                raise ResourceException(e)
        else:
            raise ResourceException("%s not found." % res_id)

        return status

    def create(self, res_id, attributes):
        """
            collection: docks
            id: Antwerp
            attributes:
                image: ....
                name: hostname
                memory (MB): ...
                cpu_share: ...
                command: ...
        """
        status = {}

        try:
            client = self.docks[res_id]
            ports = []
            volumes = {}
            binds = {}
            if attributes.get('ports'):
                for port in attributes['ports']:
                    ports.append("%s:%s" % (port['local'], port['remote']))

            if attributes.get('volumes'):
                for vol in attributes['volumes']:
                    volumes[vol['remote']] = {}
                    binds[vol['local']] = vol['remote']

            container_id = client.create_container(attributes['image'],
                                                   attributes['command'],
                                                   ports=ports,
                                                   volumes=volumes)['Id']
            client.start(container_id, binds=binds)
            try:
                status = self.read(res_id, {'container': container_id})
            except ResourceException:
                raise ResourceException("The container does not exist or is "
                                        "terminated.")
        except KeyError as e:
            raise ResourceException("%s attribute missing." % e)

        return status

    def update(self, res_id, attributes):
        """
        """
        return self.create(res_id, attributes)

    def delete(self, res_id, attributes):
        """
        """
        status = {}

        try:
            client = self.docks[res_id]
            client.kill(attributes['container'])
            status['Id'] = attributes['container']
        except KeyError as e:
            raise ResourceException("%s attribute missing." % e)

        return status

    def ping(self):
        result = self.read(res_id='')
        msg = OutgoingMessage(collection=self.__resource__,
                              status=result,
                              msg_type='status',
                              status_message=True)
        task = AmqpTask(msg)
        self.publish(task)

    def _load_config_file(self):
        """ Loads the configuration file.
        """
        conf = {}
        parser = ConfigParser.SafeConfigParser()
        parser.read(self.DOCKS_CONFIG_FILE)
        for section in parser.sections():
            conf[section] = dict(parser.items(section))

        return conf
