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
import uuid
import tempfile
import testtools

# Third Party Imports
import mock
from moto import mock_ec2
from boto.vpc import VPCConnection
from boto.exception import EC2ResponseError, BotoServerError

# Cloudify Imports is imported and used in operations
from cloudify_aws.ec2 import instance
from cloudify.state import current_ctx
from cloudify.mocks import MockContext
from cloudify.mocks import MockNodeContext
from cloudify.context import BootstrapContext
from cloudify_aws import constants, connection
from cloudify.mocks import MockCloudifyContext
from cloudify.exceptions import NonRecoverableError

TEST_AMI_IMAGE_ID = 'ami-e214778a'
TEST_INSTANCE_TYPE = 't1.micro'
FQDN = '((?:[a-z][a-z\\.\\d\\-]+)\\.(?:[a-z][a-z\\-]+))(?![\\w\\.])'
SUBNET_ID = 'subnet-0123abcd'
TEST_AVAILABILITY_ZONE = 'us-east-1b'


class TestInstance(testtools.TestCase):

    def create_vpc_client(self):
        return VPCConnection()

    def mock_ctx(self, test_name, retry_number=0, operation_name='create'):
        """ Creates a mock context for the instance
            tests
        """

        test_node_id = test_name
        test_properties = {
            constants.AWS_CONFIG_PROPERTY: {},
            'use_external_resource': False,
            'resource_id': '',
            'name': '',
            'tags': {},
            'image_id': TEST_AMI_IMAGE_ID,
            'instance_type': TEST_INSTANCE_TYPE,
            'cloudify_agent': {},
            'agent_config': {},
            'use_password': False,
            'parameters': {
                'security_group_ids': ['sg-73cd3f1e'],
                'instance_initiated_shutdown_behavior': 'stop'
            }
        }

        operation = {
            'name': operation_name,
            'retry_number': retry_number
        }
        ctx = MockCloudifyContext(
                node_id=test_node_id,
                deployment_id=str(uuid.uuid4()),
                properties=test_properties,
                operation=operation,
                provider_context={'resources': {}}
        )
        ctx.node.type_hierarchy = ['cloudify.nodes.Compute']
        return ctx

    def create_instance_for_checking(self):
        return instance.Instance()

    @mock_ec2
    @mock.patch('cloudify_aws.utils.get_single_connected_node_by_type')
    def test_key_pair_and_relationship(self, *_):
        """tests that key pair is not provided by both a property
        and via relationship
        """

        name = 'test_key_pair_and_relationship'
        ctx = self.mock_ctx(name)
        current_ctx.set(ctx=ctx)

        ctx.node.properties['use_password'] = True
        private_key_dir = tempfile.mkdtemp()
        private_key_path = '{0}/{1}.pem' \
            .format(private_key_dir, name)
        test_instance = self.create_instance_for_checking()

        ex = self.assertRaises(NonRecoverableError,
                               test_instance._get_private_key,
                               private_key_path=private_key_path)
        self.assertIn("server can't both have a",
                      ex.message)

    @mock_ec2
    def test_no_key_pair_file(self, *_):
        """tests correct error is thrown when key file is missing
        """

        name = 'test_no_key_pair_file'
        ctx = self.mock_ctx(name)
        current_ctx.set(ctx=ctx)

        ctx.node.properties['use_password'] = True
        private_key_dir = tempfile.mkdtemp()
        private_key_path = '{0}/{1}.pem' \
            .format(private_key_dir, name)
        test_instance = self.create_instance_for_checking()

        with mock.patch(
                'cloudify_aws.utils.get_single_connected_node_by_type') \
                as mock_get_single_connected_node_by_type:
            mock_get_single_connected_node_by_type.return_value = None
            ex = self.assertRaises(NonRecoverableError,
                                   test_instance._get_private_key,
                                   private_key_path=private_key_path)
            self.assertIn("Cannot locate key file; expected file path",
                          ex.message)

    @mock_ec2
    def test_relationship_key_pair(self, *_):
        """tests finding a key file via relationship
        """

        name = 'test_relationship_key_pair'
        ctx = self.mock_ctx(name)
        current_ctx.set(ctx=ctx)

        ctx.node.properties['use_password'] = True
        private_key_dir = tempfile.mkdtemp()
        private_key_path = '{0}/{1}.pem' \
            .format(private_key_dir, name)
        open(private_key_path, 'w').close()

        key_pair_node = MockNodeContext(properties={
            'private_key_path': private_key_path
        })
        test_instance = self.create_instance_for_checking()

        with mock.patch(
                'cloudify_aws.utils.get_single_connected_node_by_type') \
                as mock_get_single_connected_node_by_type:
            mock_get_single_connected_node_by_type.return_value = key_pair_node
            output = test_instance._get_private_key('')
            self.assertEqual(private_key_path, output)

    @mock_ec2
    @mock.patch('cloudify_aws.utils.get_single_connected_node_by_type')
    @mock.patch('cloudify_aws.ec2.instance.Instance.__init__')
    def test_bootstrap_context_key_pair(self, *_):
        """tests finding a key file via bootstrap context
        """

        name = 'test_bootstrap_context_key_pair'
        private_key_dir = tempfile.mkdtemp()
        private_key_path = '{0}/{1}.pem' \
            .format(private_key_dir, name)
        open(private_key_path, 'w').close()

        cloudify_agent = MockContext()
        cloudify_agent['agent_key_path'] = private_key_path

        bootstrap_ctx = BootstrapContext({
            'cloudify_agent': cloudify_agent
        })

        ctx = MockCloudifyContext(bootstrap_context=bootstrap_ctx,
                                  node_name=name)
        current_ctx.set(ctx=ctx)

        with mock.patch(
                'cloudify_aws.utils.get_single_connected_node_by_type') \
                as mock_get_connected:
            with mock.patch('cloudify_aws.ec2.instance.Instance.__init__') \
                    as mock_instance_init:
                mock_instance_init.return_value = None
                mock_get_connected.return_value = None
                output = instance.Instance()._get_private_key('')
                self.assertEqual(private_key_path, output)

    @mock_ec2
    @mock.patch('cloudify_aws.utils.get_single_connected_node_by_type')
    @mock.patch('cloudify_aws.ec2.instance.Instance._get_private_key')
    def test_windows_runtime_property_created(self, *_):
        """tests that the generated windows password is saved as
        a runtime property
        """

        ctx = self.mock_ctx('test_windows_runtime_property_created')
        current_ctx.set(ctx=ctx)

        ec2_client = connection.EC2ConnectionClient().client()
        reservation = ec2_client.run_instances(
                TEST_AMI_IMAGE_ID, instance_type=TEST_INSTANCE_TYPE)
        instance_id = reservation.instances[0].id
        ctx.instance.runtime_properties['aws_resource_id'] = instance_id
        ctx.node.properties['use_password'] = True

        with mock.patch(
                'cloudify_aws.ec2.instance.Instance._get_windows_password') \
                as mock_get_windows_password:
            mock_get_windows_password.return_value = 'pass'
            instance.start(ctx=ctx)
            self.assertEqual(ctx.instance.runtime_properties
                             [constants.ADMIN_PASSWORD_PROPERTY], 'pass')

    @mock_ec2
    def test_run_instances_clean(self):
        """ this tests that the instance create function
        adds the runtime_properties
        """

        ctx = self.mock_ctx('test_run_instances_clean')
        current_ctx.set(ctx=ctx)
        instance.create(ctx=ctx)
        self.assertIn('aws_resource_id',
                      ctx.instance.runtime_properties.keys())

    @mock_ec2
    def test_with_userdata_clean(self):
        """ this tests that handle user data returns the expected output
        """

        ctx = self.mock_ctx('test_with_userdata_clean')
        ctx.agent.init_script = lambda: 'SCRIPT'
        ctx.node.properties['agent_config']['install_method'] = 'init_script'
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()

        handle_userdata_output = \
            test_instance._handle_userdata(ctx.node.properties['parameters'])
        expected_userdata = 'SCRIPT'
        self.assertIn(expected_userdata,
                      handle_userdata_output.get('user_data'))

    @mock_ec2
    def test_with_existing_userdata_clean(self):
        """ this tests that handle user data returns the expected output when existing
        """

        ctx = self.mock_ctx('test_with_existing_userdata_clean')
        ctx.agent.init_script = lambda: 'EXISTING'
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()

        handle_userdata_output = \
            test_instance._handle_userdata(ctx.node.properties['parameters'])
        expected_userdata = 'EXISTING'
        self.assertIn(
                expected_userdata, handle_userdata_output.get('user_data'))

    @mock_ec2
    def test_with_both_userdata_clean(self):
        """ this tests that handle user data returns the expected output when merging
        """

        ctx = self.mock_ctx('test_with_existing_userdata_clean')
        ctx.agent.init_script = lambda: '#! SCRIPT'
        ctx.node.properties['agent_config']['install_method'] = 'init_script'
        ctx.node.properties['parameters']['user_data'] = '#! EXISTING'
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()
        handle_userdata_output = \
            test_instance._handle_userdata(ctx.node.properties['parameters'])
        self.assertTrue(handle_userdata_output['user_data'].startswith(
                'Content-Type: multi'))

    @mock_ec2
    def test_without_userdata_clean(self):
        """ this tests that handle user data returns the expected output
        when there is no init script specified in agent config
        """

        ctx = self.mock_ctx('test_run_instances_with_user_data_clean')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()
        handle_userdata_output = \
            test_instance._handle_userdata(ctx.node.properties['parameters'])
        self.assertNotIn('user_data', handle_userdata_output)

    @mock_ec2
    @mock.patch('boto.ec2.instance.Instance.placement', TEST_AVAILABILITY_ZONE)
    def test_run_instances_provider_context_good_subnet(self):
        """ this tests that the instance create function
        adds the runtime_properties
        """

        vpc = self.create_vpc_client().create_vpc('10.10.10.0/16')
        subnet = self.create_vpc_client().create_subnet(
                vpc.id, '10.10.10.0/24',
                availability_zone=TEST_AVAILABILITY_ZONE)
        ctx = self.mock_ctx('test_run_instances_provider_context_good_subnet')
        ctx.provider_context['resources'] = {
            constants.VPC['AWS_RESOURCE_TYPE']: {
                'id': vpc.id,
                'external_resource': True
            },
            constants.SUBNET['AWS_RESOURCE_TYPE']: {
                'id': subnet.id,
                'external_resource': True
            },
            constants.AGENTS_AWS_INSTANCE_PARAMETERS: {
                'placement': TEST_AVAILABILITY_ZONE
            }
        }
        current_ctx.set(ctx=ctx)
        instance.create(ctx=ctx)
        self.assertIn('aws_resource_id',
                      ctx.instance.runtime_properties.keys())
        self.assertIn('subnet_id',
                      ctx.instance.runtime_properties.keys())
        self.assertEquals(subnet.id,
                          ctx.instance.runtime_properties['subnet_id'])
        self.assertIn('vpc_id',
                      ctx.instance.runtime_properties.keys())
        self.assertEquals(vpc.id,
                          ctx.instance.runtime_properties['vpc_id'])
        self.assertIn('placement',
                      ctx.instance.runtime_properties.keys())
        self.assertEquals(TEST_AVAILABILITY_ZONE,
                          ctx.instance.runtime_properties['placement'])

    @mock_ec2
    def test_run_instances_provider_context_bad_subnet(self):
        """ this tests that the instance create function
        adds the runtime_properties
        """

        ctx = self.mock_ctx('test_run_instances_provider_context_bad_subnet')
        ctx.provider_context['resources'] = {
            constants.SUBNET['AWS_RESOURCE_TYPE']: {
                'id': SUBNET_ID,
                'external_resource': True
            }
        }
        current_ctx.set(ctx=ctx)
        e = self.assertRaises(NonRecoverableError,
                              instance.create, ctx=ctx)
        self.assertIn(SUBNET_ID, e.message)

    @mock_ec2
    def test_stop_clean(self):
        """
        this tests that the instance stop function stops the
        isntance
        """

        ctx = self.mock_ctx('test_stop_clean')
        current_ctx.set(ctx=ctx)

        ec2_client = connection.EC2ConnectionClient().client()
        reservation = ec2_client.run_instances(
                TEST_AMI_IMAGE_ID, instance_type=TEST_INSTANCE_TYPE)
        instance_id = reservation.instances[0].id
        ctx.instance.runtime_properties['aws_resource_id'] = instance_id
        ctx.instance.runtime_properties['private_dns_name'] = '0.0.0.0'
        ctx.instance.runtime_properties['public_dns_name'] = '0.0.0.0'
        ctx.instance.runtime_properties['public_ip_address'] = '0.0.0.0'
        ctx.instance.runtime_properties['ip'] = '0.0.0.0'
        ctx.instance.runtime_properties['placement'] = TEST_AVAILABILITY_ZONE
        instance.stop(ctx=ctx)
        reservations = ec2_client.get_all_reservations(instance_id)
        instance_object = reservations[0].instances[0]
        state = instance_object.update()
        self.assertEqual(state, 'stopped')

    @mock_ec2
    def test_start_clean(self):
        """ this tests that the instance start function
        starts an instance.
        """

        ctx = self.mock_ctx('test_start_clean')
        current_ctx.set(ctx=ctx)

        ec2_client = connection.EC2ConnectionClient().client()
        reservation = ec2_client.run_instances(
                TEST_AMI_IMAGE_ID, instance_type=TEST_INSTANCE_TYPE)
        instance_id = reservation.instances[0].id
        ctx.instance.runtime_properties['aws_resource_id'] = instance_id
        ec2_client.stop_instances(instance_id)
        instance.start(ctx=ctx)
        reservations = ec2_client.get_all_reservations(instance_id)
        instance_object = reservations[0].instances[0]
        state = instance_object.update()
        self.assertEqual(state, 'running')

    @mock_ec2
    def test_terminate_clean(self):
        """ this tests that the instance.terminate function
            terminates the instance
        """

        ctx = self.mock_ctx('test_terminate_clean')
        current_ctx.set(ctx=ctx)

        ec2_client = connection.EC2ConnectionClient().client()
        reservation = ec2_client.run_instances(
                TEST_AMI_IMAGE_ID, instance_type=TEST_INSTANCE_TYPE)
        instance_id = reservation.instances[0].id
        ctx.instance.runtime_properties['aws_resource_id'] = instance_id
        instance.delete(ctx=ctx)
        reservations = ec2_client.get_all_reservations(instance_id)
        instance_object = reservations[0].instances[0]
        state = instance_object.update()
        self.assertEqual(state, 'terminated')

    @mock_ec2
    def test_start_bad_id(self):
        """this tests that start fails when given an invalid
           instance_id and the proper error is raised
        """

        ctx = self.mock_ctx('test_start_bad_id')
        current_ctx.set(ctx=ctx)

        ctx.instance.runtime_properties['aws_resource_id'] = 'bad_id'
        ctx.instance.runtime_properties['reservation_id'] = 'r-54ce20b4'
        ex = self.assertRaises(NonRecoverableError,
                               instance.start, ctx=ctx)
        self.assertIn('no instance with id bad_id exists in this account',
                      ex.message)

    @mock_ec2
    def test_stop_bad_id(self):
        """ this tests that stop fails when given an invalid
            instance_id and the proper error is raised
        """

        ctx = self.mock_ctx('test_stop_bad_id')
        current_ctx.set(ctx=ctx)

        ctx.instance.runtime_properties['aws_resource_id'] = 'bad_id'
        ctx.instance.runtime_properties['private_dns_name'] = '0.0.0.0'
        ctx.instance.runtime_properties['public_dns_name'] = '0.0.0.0'
        ctx.instance.runtime_properties['public_ip_address'] = '0.0.0.0'
        ctx.instance.runtime_properties['ip'] = '0.0.0.0'
        ex = self.assertRaises(
                NonRecoverableError, instance.stop, ctx=ctx)
        self.assertIn('InvalidInstanceID', ex.message)

    @mock_ec2
    def test_terminate_bad_id(self):
        """ this tests that a terminate fails when given an
            invalid instance_id and the proper error is raised
        """

        ctx = self.mock_ctx('test_terminate_bad_id')
        current_ctx.set(ctx=ctx)

        ctx.instance.runtime_properties['aws_resource_id'] = 'bad_id'
        ctx.instance.runtime_properties['private_dns_name'] = '0.0.0.0'
        ctx.instance.runtime_properties['public_dns_name'] = '0.0.0.0'
        ctx.instance.runtime_properties['public_ip_address'] = '0.0.0.0'
        ctx.instance.runtime_properties['ip'] = '0.0.0.0'
        ex = self.assertRaises(NonRecoverableError,
                               instance.delete, ctx=ctx)
        self.assertIn('InvalidInstanceID.NotFound', ex.message)

    @mock_ec2
    def test_run_instances_bad_subnet_id(self):
        """ This tests that the NonRecoverableError is triggered
            when an non existing subnet_id is included in the create
            statement
        """

        ctx = self.mock_ctx('test_run_instances_bad_subnet_id')
        ctx.node.properties['parameters']['subnet_id'] = 'test'
        current_ctx.set(ctx=ctx)

        ex = self.assertRaises(
                NonRecoverableError, instance.create, ctx=ctx)
        self.assertIn('InvalidSubnetID.NotFound', ex.message)

    @mock_ec2
    def test_run_instances_external_resource(self):
        """ this tests that the instance create function adds
        the runtime_properties
        """
        ctx = self.mock_ctx('test_run_instances_external_resource')
        current_ctx.set(ctx=ctx)

        ec2_client = connection.EC2ConnectionClient().client()
        reservation = ec2_client.run_instances(
                TEST_AMI_IMAGE_ID, instance_type=TEST_INSTANCE_TYPE)
        instance_id = reservation.instances[0].id
        ctx.node.properties['use_external_resource'] = True
        ctx.node.properties['resource_id'] = instance_id
        instance.create(ctx=ctx)
        self.assertIn('aws_resource_id',
                      ctx.instance.runtime_properties.keys())

    @mock_ec2
    def test_validation_external_resource(self):
        """ this tests that creation_validation raises an error
        when a use_external_resource is true but a bad instance_id
        is given.
        """
        ctx = self.mock_ctx('test_validation_external_resource')
        ctx.node.properties['use_external_resource'] = True
        ctx.node.properties['resource_id'] = 'bad_id'
        current_ctx.set(ctx=ctx)

        ex = self.assertRaises(
                NonRecoverableError,
                instance.creation_validation, ctx=ctx)
        self.assertIn(
                'External resource, but the supplied instance',
                ex.message)

    @mock_ec2
    def test_validation_no_external_resource_is(self):
        """ this tests that creation_validation raises an error
        when a use_external_resource is false but a good instance_id
        is given.
        """
        ctx = self.mock_ctx('test_validation_no_external_resource_is')
        current_ctx.set(ctx=ctx)

        ec2_client = connection.EC2ConnectionClient().client()
        reservation = ec2_client.run_instances(
                TEST_AMI_IMAGE_ID, instance_type=TEST_INSTANCE_TYPE)
        instance_id = reservation.instances[0].id
        ctx.node.properties['use_external_resource'] = False
        ctx.node.properties['resource_id'] = instance_id
        ex = self.assertRaises(
                NonRecoverableError,
                instance.creation_validation, ctx=ctx)
        self.assertIn(
                'Not external resource, but the supplied',
                ex.message)

    @mock_ec2
    def test_no_instance_get_instance_from_id(self):
        """ this tests that a NonRecoverableError is thrown
        when a nonexisting instance_id is provided to the
        get_instance_from_id function
        """
        ctx = self.mock_ctx('test_no_instance_get_instance_from_id')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()

        instance_id = 'bad_id'
        ctx.instance.runtime_properties['aws_resource_id'] = instance_id
        output = test_instance._get_instance_from_id(instance_id)
        self.assertIsNone(output)

    @mock_ec2
    def test_get_private_dns_name(self):
        """ This checks that _get_instance_attribute
        sets the correct runtime property and it is an FQDN
        """

        ctx = self.mock_ctx('test_get_private_dns_name')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()

        ec2_client = connection.EC2ConnectionClient().client()
        reservation = ec2_client.run_instances(
                TEST_AMI_IMAGE_ID, instance_type=TEST_INSTANCE_TYPE)
        ctx.instance.runtime_properties['aws_resource_id'] = \
            reservation.instances[0].id
        property_name = 'private_dns_name'
        dns_name = test_instance._get_instance_attribute(
                property_name)
        self.assertRegexpMatches(dns_name, FQDN)

    @mock_ec2
    def test_get_all_instances_bad_id(self):
        """this checks that _get_all_instances returns None
        when there is no such instance.
        """

        ctx = self.mock_ctx('test_get_all_instances_bad_id')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()

        output = test_instance._get_all_instances(
                list_of_instance_ids='test_get_all_instances_bad_id')
        self.assertIsNone(output)

    @mock_ec2
    def test_get_all_instances_error(self):
        """this checks that _get_all_instances raises an error
        when get_all_reservations fails due
        to response error and boto server error.
        """

        ctx = self.mock_ctx('test_get_all_instances_error')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()

        with mock.patch(
                'boto.ec2.connection.EC2Connection.get_all_reservations') \
                as mock_get_all_reservations:

            with self.assertRaisesRegexp(
                    EC2ResponseError,
                    'InvalidInstanceID.NotFound'):
                mock_get_all_reservations.side_effect = EC2ResponseError(
                        mock.Mock(return_value={'status': 404}),
                        'InvalidInstanceID.NotFound')
                output = test_instance._get_all_instances(
                        list_of_instance_ids='')
                self.assertIsNone(output)

            mock_get_all_reservations.side_effect = BotoServerError(
                    mock.Mock(return_value={'status': 404}),
                    'ServerError')
            ex = self.assertRaises(
                    NonRecoverableError, test_instance._get_all_instances,
                    list_of_instance_ids='')
            self.assertIn('ServerError', ex.message)

    @mock_ec2
    def test_get_instance_attribute_no_instance(self):
        """ This tests that _get_instance_attribute raises an
        error when use_external_resource is true and there
        is no such resource.
        """

        ctx = self.mock_ctx('test_get_instance_attribute_no_instance')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()
        ctx.instance.runtime_properties['aws_resource_id'] = \
            'i-4339wSD9'
        ctx.node.properties['use_external_resource'] = True
        ex = self.assertRaises(
                NonRecoverableError,
                test_instance._get_instance_attribute,
                'state_code')
        self.assertIn(
                'External resource, but the supplied', ex.message)

    @mock_ec2
    def test_get_instance_attribute_multiple_instances(self):
        """ This tests that _get_instance_attribute raises an
        error when there is more than one resource.
        """

        ctx = self.mock_ctx('test_get_instance_attribute_multiple_instances')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()
        ctx.instance.runtime_properties['aws_resource_id'] = \
            'i-4339wSD9'

        with mock.patch('cloudify_aws.ec2.instance.Instance.'
                        '_get_instances_from_reservation_id') \
                as mock_get_instances_from_reservation_id:
            mock_get_instances_from_reservation_id.return_value = \
                ['i-0000000', 'i-1111111']

            with self.assertRaisesRegexp(
                    NonRecoverableError,
                    'because more than one instance with id'):
                test_instance._get_instance_attribute('state_code')

    @mock_ec2
    def test_get_instances_from_reservation_id(self):
        """ This tests that _get_instances_from_reservation_id raises an
        error when get_all_instances errors.
        """

        ctx = self.mock_ctx('test_get_instance_attribute_multiple_instances')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()
        ctx.instance.runtime_properties['aws_resource_id'] = \
            'i-4339wSD9'
        ctx.instance.runtime_properties['reservation_id'] = 'r-54ce20b4'
        with mock.patch('boto.ec2.connection.EC2Connection'
                        '.get_all_instances') \
                as mock_get_all_instances:

            mock_get_all_instances.side_effect = EC2ResponseError(
                    mock.Mock(return_value={'status': 404}),
                    'error')
            ex = self.assertRaises(
                    NonRecoverableError, test_instance
                    ._get_instances_from_reservation_id)
            self.assertIn('error', ex.message)

    @mock_ec2
    def test_get_network_interfaces(self):
        ctx = self.mock_ctx('test_get_network_interfaces')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()
        ctx.instance.runtime_properties['aws_resource_id'] = \
            'i-4339wSD9'
        network_interface = test_instance._get_network_interfaces(
                [{'network_interface_id': 'eni-121212'}])
        self.assertIn('NetworkInterfaceSpecification', str(network_interface))

    @mock_ec2
    @mock.patch('cloudify_aws.ec2.instance.Instance._get_network_interfaces',
                return_true='qwe')
    def test_get_instance_parameters(self, *_):
        """ This tests that the _get_instance_parameters
        function returns a dict with the correct structure.
        """

        ctx = self.mock_ctx(
                'test_get_instance_parameters')
        current_ctx.set(ctx=ctx)
        test_instance = self.create_instance_for_checking()

        ctx.node.properties['image_id'] = 'abc'
        ctx.node.properties['instance_type'] = 'efg'
        ctx.node.properties['parameters']['image_id'] = 'abcd'
        ctx.node.properties['parameters']['key_name'] = 'xyz'
        ctx.node.properties['parameters']['network_interfaces'] = 'qwe'
        parameters = test_instance._get_instance_parameters()
        self.assertIn('abcd', parameters['image_id'])
        self.assertIn('xyz', parameters['key_name'])
        self.assertIn('efg', parameters['instance_type'])
        self.assertIn('qwe', parameters['network_interfaces'])

    @mock_ec2
    def test_creation_validation_image_id(self):
        """This tests that creation validation gets to image_id
        it will return NonRecoverableError if the image_id
        doesn't exist.
        """

        ctx = self.mock_ctx('test_creation_validation_image_id')
        current_ctx.set(ctx=ctx)
        ctx.node.properties['image_id'] = 'abc'
        ctx.node.properties['instance_type'] = 'efg'
        with self.assertRaisesRegexp(
                NonRecoverableError,
                'Invalid id:'):
            instance.creation_validation(ctx=ctx)

    @mock_ec2
    def test_start_and_tag_name(self):
        """ this tests that the instance start function
        starts an instance and add tags.
        """

        ctx = self.mock_ctx('test_start_clean')
        ec2_client = connection.EC2ConnectionClient().client()
        reservation = ec2_client.run_instances(
                TEST_AMI_IMAGE_ID, instance_type=TEST_INSTANCE_TYPE)
        instance_id = reservation.instances[0].id
        ctx.instance.runtime_properties['aws_resource_id'] = instance_id
        ec2_client.stop_instances(instance_id)
        ctx.node.properties['name'] = 'test_start_and_tag_name'
        current_ctx.set(ctx=ctx)
        instance.start(ctx=ctx)
        reservations = ec2_client.get_all_reservations(instance_id)
        instance_object = reservations[0].instances[0]
        self.assertEquals(instance_object.tags.get('Name'),
                          ctx.node.properties['name'])
        self.assertEquals(instance_object.tags.get('resource_id'),
                          ctx.instance.id)
        self.assertEquals(instance_object.tags.get('deployment_id'),
                          ctx.deployment.id)

    @mock_ec2
    def test_modify_attributes(self):
        """This tests that modify attributes function
        modifies an instance attribute and return True.
        """

        ctx = self.mock_ctx('test_modify_attributes')
        current_ctx.set(ctx=ctx)
        instance.create(ctx=ctx)
        new_attributes = {'blockDeviceMapping': ['/dev/sda1=true']}
        message = instance.modify_attributes(new_attributes)

        self.assertEquals(True, message)

    @mock_ec2
    def test_modify_attributes_bad_attribute(self):
        """This tests that modify attributes function
        raises an NonRecoverableError when bad attribute
        is given.
        """

        ctx = self.mock_ctx('test_modify_attributes_bad_attribute')
        current_ctx.set(ctx=ctx)
        new_attributes = {'sourceDestCheck': 'bad'}
        self.assertIsNone(instance.modify_attributes(new_attributes))

    @mock_ec2
    def test_modify_attributes_raises_error(self):
        """This tests that modify attributes function
        raises an error when execute fails.
        """

        ctx = self.mock_ctx('test_modify_attributes_raises_error')
        current_ctx.set(ctx=ctx)
        instance.create(ctx=ctx)
        new_attributes = {'blockDeviceMapping': ['/dev/sda1=true']}

        with mock.patch('boto.ec2.connection.EC2Connection.'
                        'modify_instance_attribute') \
                as mock_modify_instance_attribute:

            mock_modify_instance_attribute.side_effect = EC2ResponseError(
                    mock.Mock(return_value={'status': 404}),
                    'error')
            ex = self.assertRaises(
                    NonRecoverableError, instance.modify_attributes,
                    new_attributes)
            self.assertIn('error', ex.message)

    @mock_ec2
    @mock.patch('cloudify_aws.ec2.instance.Instance._get_image')
    def test_creation_validation_unavailable_image(self, *_):
        """This tests that creation validation function
        return NonRecoverableError if the image_id
        is not available.
        """

        ctx = self.mock_ctx('test_creation_validation_unavailable_image')
        current_ctx.set(ctx=ctx)
        ctx.node.properties['image_id'] = TEST_AMI_IMAGE_ID
        ctx.node.properties['instance_type'] = TEST_INSTANCE_TYPE

        with self.assertRaisesRegexp(
                        NonRecoverableError,
                        'not available to this account'):
            instance.creation_validation(ctx=ctx)

    @mock_ec2
    def test_creation_validation_no_image(self):
        """This tests that creation validation function
        return NonRecoverableError if the image_id
        was not provided.
        """

        ctx = self.mock_ctx('test_creation_validation_no_image')
        current_ctx.set(ctx=ctx)
        ctx.node.properties['image_id'] = ''
        ctx.node.properties['instance_type'] = TEST_INSTANCE_TYPE

        with self.assertRaisesRegexp(
                NonRecoverableError,
                'No image_id was provided'):
            instance.creation_validation(ctx=ctx)

    @mock_ec2
    @mock.patch('cloudify_aws.ec2.instance.Instance.'
                '_get_instances_from_reservation_id')
    def test__run_instances_retry(self, *_):
        """This tests that the function run instances
        runs when retry.
        """

        name = 'test__run_instances_retry'
        ctx = self.mock_ctx(name, 1)
        current_ctx.set(ctx=ctx)

        args = dict(
                image_id=TEST_AMI_IMAGE_ID,
                instance_type=TEST_INSTANCE_TYPE)

        ctx.instance.runtime_properties['aws_resource_id'] = None
        test_instance = self.create_instance_for_checking()
        test_instance._run_instances_if_needed(create_args=args)

    @mock_ec2
    def test__run_instances_retry_no_instance(self, *_):
        """This tests that the function run instances
        with retry raises NonRecoverableError when the
        instance failed.
        """

        name = 'test__run_instances_retry_no_instance'
        ctx = self.mock_ctx(name, 1)
        current_ctx.set(ctx=ctx)
        args = dict(
                image_id=TEST_AMI_IMAGE_ID,
                instance_type=TEST_INSTANCE_TYPE)

        test_instance = self.create_instance_for_checking()

        with mock.patch(
                'cloudify_aws.ec2.instance.Instance.'
                '_get_instances_from_reservation_id') \
                as mock_get_instances_from_reservation_id:
            mock_get_instances_from_reservation_id.return_value = None

            with self.assertRaisesRegexp(
                    NonRecoverableError,
                    'Instance failed for an unknown reason'):
                test_instance._run_instances_if_needed(create_args=args)

    @mock_ec2
    def test__run_instances_retry_multiple_instances(self, *_):
        """This tests that the function run instances
        with retry raises NonRecoverableError when the
        instance failed.
        """

        name = 'test__run_instances_retry_multiple_instances'
        ctx = self.mock_ctx(name, 1)
        current_ctx.set(ctx=ctx)
        args = dict(
                image_id=TEST_AMI_IMAGE_ID,
                instance_type=TEST_INSTANCE_TYPE)

        test_instance = self.create_instance_for_checking()

        with mock.patch(
                'cloudify_aws.ec2.instance.Instance.'
                '_get_instances_from_reservation_id') \
                as mock_get_instances_from_reservation_id:
            mock_get_instances_from_reservation_id.return_value = \
                ['i-0000000', 'i-1111111']

            with self.assertRaisesRegexp(
                    NonRecoverableError,
                    'More than one instance was created'):
                test_instance._run_instances_if_needed(create_args=args)

    @mock_ec2
    def test_with_block_storage_params(self):
        """ The user provides a list of block device parameters
        """

        ctx = self.mock_ctx('test_with_block_storage_params')
        block_device_map = {
            'dev_sda1': {
                'size': 100
            }
        }

        ctx.node.properties['parameters']['block_device_map'] = \
            block_device_map
        current_ctx.set(ctx=ctx)
        instance.create(ctx=ctx)
        instance_id = ctx.instance.runtime_properties['aws_resource_id']
        ec2_client = connection.EC2ConnectionClient().client()
        reservations = ec2_client.get_all_reservations(instance_id)
        instance_object = reservations[0].instances[0]
        device_name = block_device_map.keys()[0]
        self.assertEquals(instance_object.block_device_mapping.keys()[0],
                          '/{0}/{1}'.format(device_name.split('_')[0],
                                            device_name.split('_')[1]))

    @mock_ec2
    def test_with_block_storage_args(self):
        """ The user provides a list of block device parameters
        """

        ctx = self.mock_ctx('test_with_block_storage_args')
        block_device_map = {
            'dev_sda1': {
                'size': 100
            }
        }

        current_ctx.set(ctx=ctx)
        instance.create(ctx=ctx, args={'block_device_map': block_device_map})
        instance_id = ctx.instance.runtime_properties['aws_resource_id']
        ec2_client = connection.EC2ConnectionClient().client()
        reservations = ec2_client.get_all_reservations(instance_id)
        instance_object = reservations[0].instances[0]
        device_name = block_device_map.keys()[0]
        self.assertEquals(instance_object.block_device_mapping.keys()[0],
                          '/{0}/{1}'.format(device_name.split('_')[0],
                                            device_name.split('_')[1]))
