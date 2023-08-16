"""
RunPod Node Provider. A RunPod pod is a node within the Sky paradigm.

Node provider is called by the Ray Autoscaler to provision new compute resources.

To show debug messages, export SKYPILOT_DEBUG=1

Class definition: https://github.com/ray-project/ray/blob/master/python/ray/autoscaler/node_provider.py
"""


import logging
from threading import RLock
from typing import Any, Dict, List, Optional

from ray.autoscaler.node_provider import NodeProvider
from ray.autoscaler.tags import TAG_RAY_CLUSTER_NAME

import runpod

logger = logging.getLogger(__name__)


class RunPodError(Exception):
    pass


def synchronized(func):
    def wrapper(self, *args, **kwargs):
        self.lock.acquire()
        try:
            return func(self, *args, **kwargs)
        finally:
            self.lock.release()

    return wrapper


class RunPodNodeProvider(NodeProvider):
    """ Node Provider for RunPod. """

    def __init__(self, provider_config: Dict[str, Any], cluster_name: str) -> None:
        """
        cached_nodes |
        api_key | The RunPod API key
        ssh_key_name | The name of the SSH key to use for the pods.
        """
        NodeProvider.__init__(self, provider_config, cluster_name)
        self.lock = RLock()
        self.cached_nodes: Dict[str, Dict[str, Any]] = {}

        # Load credentials
        self.api_key =  runpod.get_credentials()['api_key']
        self.ssh_key_name =  runpod.get_credentials()['ssh_key_name']

    @synchronized
    def _get_filtered_nodes(self, tag_filters):
        running_instances = list_instances(self.api_key)

        ########
        # TODO #
        ########
        self.cached_nodes =  # TODO Filter running instances by tag_filters

        return self.cached_nodes

    def non_terminated_nodes(self, tag_filters):
        """Return a list of node ids filtered by the specified tags dict.

        This list must not include terminated nodes. For performance reasons,
        providers are allowed to cache the result of a call to
        non_terminated_nodes() to serve single-node queries
        (e.g. is_running(node_id)). This means that non_terminated_nodes()
        must be called again to refresh results.
        """
        nodes = self._get_filtered_nodes(tag_filters=tag_filters)
        return [k for k, _ in nodes.items()]

    def is_running(self, node_id):
        """Return whether the specified node is running."""
        return self._get_cached_node(node_id=node_id) is not None

    def is_terminated(self, node_id):
        """Return whether the specified node is terminated."""
        return self._get_cached_node(node_id=node_id) is None

    def node_tags(self, node_id):
        """Returns the tags of the given node (string dict)."""
        return self._get_cached_node(node_id=node_id)['tags']

    def external_ip(self, node_id):
        """Returns the external ip of the given node."""
        return self._get_cached_node(node_id=node_id)['ip']

    def internal_ip(self, node_id):
        """Returns the internal ip (Ray ip) of the given node."""
        return self._get_cached_node(node_id=node_id)['ip']

    def create_node(self, node_config, tags, count):
        """
        Creates a pod on RunPod.
        Creates a number of nodes within the namespace.

        Currently the `InstanceType` will be the gpu_type for the pod.
        """
        assert count == 1, count   # Only support 1-node clusters for now

        # Get the tags
        config_tags = node_config.get('tags', {}).copy()
        config_tags.update(tags)
        config_tags[TAG_RAY_CLUSTER_NAME] = self.cluster_name

        # Create node
        instance_type = node_config['InstanceType']
        region = self.provider_config['region']

        # vm_id = launch(name=self.cluster_name,
        #                instance_type=ttype,
        #                region=region,
        #                api_key=self.api_key
        #                ssh_key_name=self.ssh_key_name)

        pod_id = runpod.create_pod(
            name=self.cluster_name,
            image_name='nvidia/cuda:12.2.0-base-ubuntu20.04',
            gpu_type_id=instance_type
        )

        if pod_id is None:
            raise RunPodError('Failed to launch instance.')

        set_tags(pod_id, config_tags, self.api_key)

        ########
        # TODO #
        ########
        # May need to poll list_instances() to wait for booting
        # to finish before returning.

    @synchronized
    def set_node_tags(self, node_id, tags):
        """Sets the tag values (string dict) for the specified node."""
        node = self._get_node(node_id)
        node['tags'].update(tags)
        set_tags(vm_id, node['tags'], self.api_key)

    def terminate_node(self, node_id):
        """Terminates the specified node."""
        remove(node_id, self.api_key)

    def _get_node(self, node_id):
        self._get_filtered_nodes({})  # Side effect: updates cache
        return self.cached_nodes.get(node_id, None)

    def _get_cached_node(self, node_id):
        if node_id in self.cached_nodes:
            return self.cached_nodes[node_id]
        return self._get_node(node_id=node_id)