########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

# Built-in Imports
import os

# Cloudify Imports
from . import constants
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError


def validate_node_property(key, ctx_node_properties):
    """Checks if the node property exists in the blueprint.

    :raises NonRecoverableError: if key not in the node's properties
    """

    if key not in ctx_node_properties:
        raise NonRecoverableError(
                '{0} is a required input. Unable to create.'.format(key))


def log_available_resources(list_of_resources):
    """This logs a list of available resources.
    """

    message = 'Available resources: \n'

    for resource in list_of_resources:
        message = '{0}{1}\n'.format(message, resource)

    ctx.logger.debug(message)


def get_external_resource_id_or_raise(operation, ctx_instance):
    """Checks if the EXTERNAL_RESOURCE_ID runtime_property is set and
    returns it.

    :param operation: A string representing what is happening.
    :param ctx_instance: The CTX Node-Instance Context.
    :returns The EXTERNAL_RESOURCE_ID runtime_property for a CTX Instance.
    :raises NonRecoverableError: If EXTERNAL_RESOURCE_ID has not been set.
    """

    ctx.logger.debug(
            'Checking if {0} in instance runtime_properties, for {0} '
            'operation.'
            .format(constants.EXTERNAL_RESOURCE_ID, operation))

    if constants.EXTERNAL_RESOURCE_ID not in ctx_instance.runtime_properties:
        raise NonRecoverableError(
                'Cannot {0} because {1} is not assigned.'
                .format(operation, constants.EXTERNAL_RESOURCE_ID))

    return ctx_instance.runtime_properties[constants.EXTERNAL_RESOURCE_ID]


def set_external_resource_id(value, ctx_instance):
    """Sets the EXTERNAL_RESOURCE_ID runtime_property for a Node-Instance.

    :param value: the desired EXTERNAL_RESOURCE_ID runtime_property
    :param ctx_instance:  The Cloudify ctx context.
    """

    ctx.logger.info(
        'Stored reference ID# {0} in Cloudify.'.format(value))
    ctx_instance.runtime_properties[constants.EXTERNAL_RESOURCE_ID] = value


def unassign_runtime_properties_from_resource(property_names, ctx_instance):
    for property_name in property_names:
        if property_name in ctx_instance.runtime_properties:
            unassign_runtime_property_from_resource(
                    property_name, ctx_instance)


def unassign_runtime_property_from_resource(property_name, ctx_instance):
    """Pops a runtime_property and reports to debug.

    :param property_name: The runtime_property to remove.
    :param ctx_instance: The CTX Node-Instance Context.
    """

    value = ctx_instance.runtime_properties.pop(property_name, None)
    ctx.logger.debug(
            'Unassigned {0} runtime property: {1}'.format(property_name,
                                                          value))


def get_target_external_resource_ids(relationship_type, ctx_instance):
    """Gets a list of target node ids connected via a relationship to a node.

    :param relationship_type: A string representing the type of relationship.
    :param ctx_instance:  The Cloudify ctx context.
    :returns a list of security group ids.
    """

    ids = []

    if not getattr(ctx_instance, 'relationships', []):
        ctx.logger.info('Skipping attaching relationships, '
                        'because none are attached to this node.')
        return ids

    for r in ctx_instance.relationships:
        if relationship_type in r.type or \
                        relationship_type in r.type_hierarchy:
            ids.append(
                    r.target.instance.runtime_properties[
                        constants.EXTERNAL_RESOURCE_ID])

    return ids


def get_resource_id():
    """Returns the resource id, if the user doesn't provide one,
    this will create one for them.

    :return resource_id: A string.
    """

    if ctx.node.properties['resource_id']:
        return ctx.node.properties['resource_id']
    elif 'private_key_path' in ctx.node.properties:
        directory_path, filename = \
            os.path.split(ctx.node.properties['private_key_path'])
        resource_id, filetype = filename.split('.')
        return resource_id

    return '{0}-{1}'.format(ctx.deployment.id, ctx.instance.id)


def get_provider_variables():

    provider_config = ctx.provider_context.get('resources', {})

    provider_context = {
        constants.AGENTS_KEYPAIR:
            provider_config.get(constants.AGENTS_KEYPAIR, {}).get('id'),
        constants.AGENTS_SECURITY_GROUP:
            provider_config.get(constants.AGENTS_SECURITY_GROUP,
                                {}).get('id'),
        constants.SUBNET['AWS_RESOURCE_TYPE']:
            provider_config.get(constants.SUBNET['AWS_RESOURCE_TYPE'],
                                {}).get('id'),
        constants.VPC['AWS_RESOURCE_TYPE']:
            provider_config.get(constants.VPC['AWS_RESOURCE_TYPE'],
                                {}).get('id'),
        constants.AGENTS_AWS_INSTANCE_PARAMETERS:
            provider_config.get(constants.AGENTS_AWS_INSTANCE_PARAMETERS, {})
    }

    return provider_context


def get_instance_or_source_node_properties():

    if ctx.type == constants.RELATIONSHIP_INSTANCE:
        return ctx.source.node.properties
    elif ctx.type == constants.NODE_INSTANCE:
        return ctx.node.properties
    else:
        raise NonRecoverableError(
                'Invalid use of ctx. '
                'get_instance_or_source_node_properties '
                'called in a context that is not {0} or {1}.'
                .format(constants.RELATIONSHIP_INSTANCE,
                        constants.NODE_INSTANCE))


def get_single_connected_node_by_type(
        passed_ctx, type_name, if_exists=False):
    nodes = get_connected_nodes_by_type(passed_ctx, type_name)
    check = len(nodes) > 1 if if_exists else len(nodes) != 1
    if check:
        raise NonRecoverableError(
                'Expected {0} one {1} node. got {2}'
                .format('at most' if if_exists else 'exactly',
                        type_name, len(nodes)))
    return nodes[0] if nodes else None


def get_connected_nodes_by_type(passed_ctx, type_name):
    return [rel.target.node for rel in passed_ctx.instance.relationships
            if rel.target.instance.runtime_properties.get(
                constants.AWS_TYPE_PROPERTY) and
            rel.target.instance.runtime_properties.get(
                    constants.AWS_TYPE_PROPERTY) == type_name]


def update_args(parameterized_args, args_from_inputs):
    ctx.logger.debug('parameterized_args: {0}'.format(parameterized_args))
    ctx.logger.debug('args_from_inputs: {0}'.format(args_from_inputs))
    parameterized_args.update(args_from_inputs if args_from_inputs else {})
    ctx.logger.debug('args passed to function: {0}'.format(parameterized_args))
    return parameterized_args
