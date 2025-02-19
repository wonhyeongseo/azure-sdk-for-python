# coding: utf-8

# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------

import unittest
from datetime import (
    datetime,
    timedelta,
    date,
)
import pytest

from azure.core.credentials import AzureSasCredential, AzureNamedKeyCredential
from azure.core.pipeline.transport import RequestsTransport
from azure.core.exceptions import (
    HttpResponseError,
    ResourceNotFoundError,
    ResourceExistsError,
    ClientAuthenticationError)

from azure.storage.queue import (
    AccessPolicy,
    AccountSasPermissions,
    ResourceTypes,
    QueueClient,
    QueueSasPermissions,
    QueueServiceClient,
    generate_account_sas,
    generate_queue_sas
)

from devtools_testutils.storage import StorageTestCase
from settings.testcase import QueuePreparer

# ------------------------------------------------------------------------------
TEST_QUEUE_PREFIX = 'pyqueuesync'
# ------------------------------------------------------------------------------

# pylint: disable=locally-disabled, multiple-statements, fixme, too-many-lines
class StorageQueueTest(StorageTestCase):
    # --Helpers-----------------------------------------------------------------
    def _get_queue_reference(self, qsc, prefix=TEST_QUEUE_PREFIX):
        queue_name = self.get_resource_name(prefix)
        queue = qsc.get_queue_client(queue_name)
        return queue

    def _create_queue(self, qsc, prefix=TEST_QUEUE_PREFIX, queue_list=None):
        queue = self._get_queue_reference(qsc, prefix)
        created = queue.create_queue()
        if queue_list is not None:
            queue_list.append(created)
        return queue

    # --Test cases for queues ----------------------------------------------
    @QueuePreparer()
    def test_create_queue(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        created = queue_client.create_queue()

        # Asserts
        self.assertTrue(created)

    @QueuePreparer()
    def test_create_queue_fail_on_exist(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        created = queue_client.create_queue()
        with self.assertRaises(ResourceExistsError):
            queue_client.create_queue()

        # Asserts
        self.assertTrue(created)

    @QueuePreparer()
    def test_create_queue_fail_on_exist_different_metadata(self, storage_account_name, storage_account_key):
        # Action
        url = self.account_url(storage_account_name, "queue")
        qsc = QueueServiceClient(url, storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        created = queue_client.create_queue()
        with self.assertRaises(ResourceExistsError):
            queue_client.create_queue(metadata={"val": "value"})

        # Asserts
        self.assertTrue(created)

    @QueuePreparer()
    def test_create_queue_with_options(self, storage_account_name, storage_account_key):
        # Action
        url = self.account_url(storage_account_name, "queue")
        qsc = QueueServiceClient(url, storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue(
            metadata={'val1': 'test', 'val2': 'blah'})
        props = queue_client.get_queue_properties()

        # Asserts
        self.assertEqual(0, props.approximate_message_count)
        self.assertEqual(2, len(props.metadata))
        self.assertEqual('test', props.metadata['val1'])
        self.assertEqual('blah', props.metadata['val2'])

    @QueuePreparer()
    def test_delete_non_existing_queue(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)

        # Asserts
        with self.assertRaises(ResourceNotFoundError):
            queue_client.delete_queue()

    @QueuePreparer()
    def test_delete_existing_queue_fail_not_exist(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)

        created = queue_client.create_queue()
        deleted = queue_client.delete_queue()

        # Asserts
        self.assertIsNone(deleted)

    @QueuePreparer()
    def test_list_queues(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queues = list(qsc.list_queues())

        # Asserts
        self.assertIsNotNone(queues)
        assert len(queues) >= 1

    @QueuePreparer()
    def test_list_queues_with_options(self, storage_account_name, storage_account_key):
        # Arrange
        prefix = 'listqueue'
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_list = []
        for i in range(0, 4):
            self._create_queue(qsc, prefix + str(i), queue_list)

        # Action
        generator1 = qsc.list_queues(
            name_starts_with=prefix,
            results_per_page=3).by_page()
        queues1 = list(next(generator1))

        generator2 = qsc.list_queues(
            name_starts_with=prefix,
            include_metadata=True).by_page(generator1.continuation_token)
        queues2 = list(next(generator2))

        # Asserts
        self.assertIsNotNone(queues1)
        self.assertEqual(3, len(queues1))
        self.assertIsNotNone(queues1[0])
        self.assertIsNone(queues1[0].metadata)
        self.assertNotEqual('', queues1[0].name)
        assert generator1.location_mode is not None
        # Asserts
        self.assertIsNotNone(queues2)
        self.assertTrue(len(queue_list) - 3 <= len(queues2))
        self.assertIsNotNone(queues2[0])
        self.assertNotEqual('', queues2[0].name)

    @QueuePreparer()
    def test_list_queues_with_metadata(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue = self._get_queue_reference(qsc)
        queue.create_queue()
        queue.set_queue_metadata(metadata={'val1': 'test', 'val2': 'blah'})

        listed_queue = list(qsc.list_queues(
            name_starts_with=queue.queue_name,
            results_per_page=1,
            include_metadata=True))[0]

        # Asserts
        self.assertIsNotNone(listed_queue)
        self.assertEqual(queue.queue_name, listed_queue.name)
        self.assertIsNotNone(listed_queue.metadata)
        self.assertEqual(len(listed_queue.metadata), 2)
        self.assertEqual(listed_queue.metadata['val1'], 'test')

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_list_queues_account_sas(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        sas_token = generate_account_sas(
            storage_account_name,
            storage_account_key,
            ResourceTypes(service=True),
            AccountSasPermissions(list=True),
            datetime.utcnow() + timedelta(hours=1)
        )

        # Act
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), credential=sas_token)
        queues = list(qsc.list_queues())

        # Assert
        self.assertIsNotNone(queues)
        assert len(queues) >= 1

    @QueuePreparer()
    def test_set_queue_metadata(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue = self._get_queue_reference(qsc)
        metadata = {'hello': 'world', 'number': '43'}
        queue.create_queue()

        # Act
        queue.set_queue_metadata(metadata)
        metadata_from_response = queue.get_queue_properties().metadata
        # Assert
        self.assertDictEqual(metadata_from_response, metadata)

    @QueuePreparer()
    def test_get_queue_metadata_message_count(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        sent_message = queue_client.send_message('message1')
        props = queue_client.get_queue_properties()

        # Asserts
        self.assertEqual('message1', sent_message.content)
        self.assertTrue(props.approximate_message_count >= 1)
        self.assertEqual(0, len(props.metadata))

    @QueuePreparer()
    def test_queue_exists(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue = self._get_queue_reference(qsc)
        queue.create_queue()

        # Act
        exists = queue.get_queue_properties()

        # Assert
        self.assertTrue(exists)

    @QueuePreparer()
    def test_queue_not_exists(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue = qsc.get_queue_client(self.get_resource_name('missing'))
        # Act
        with self.assertRaises(ResourceNotFoundError):
            queue.get_queue_properties()

        # Assert

    @QueuePreparer()
    def test_put_message(self, storage_account_name, storage_account_key):
        # Action.  No exception means pass. No asserts needed.
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        message = queue_client.send_message('message4')

        # Asserts
        self.assertIsNotNone(message)
        self.assertNotEqual('', message.id)
        self.assertIsInstance(message.inserted_on, datetime)
        self.assertIsInstance(message.expires_on, datetime)
        self.assertNotEqual('', message.pop_receipt)
        self.assertEqual('message4', message.content)

    @QueuePreparer()
    def test_put_message_large_time_to_live(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        # There should be no upper bound on a queue message's time to live
        queue_client.send_message('message1', time_to_live=1024*1024*1024)

        # Act
        messages = queue_client.peek_messages()

        # Assert
        self.assertGreaterEqual(
            messages[0].expires_on,
            messages[0].inserted_on + timedelta(seconds=1024 * 1024 * 1024 - 3600))

    @QueuePreparer()
    def test_put_message_infinite_time_to_live(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1', time_to_live=-1)

        # Act
        messages = queue_client.peek_messages()

        # Assert
        self.assertEqual(messages[0].expires_on.year, date.max.year)

    @QueuePreparer()
    def test_get_messages(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        message = next(queue_client.receive_messages())

        # Asserts
        self.assertIsNotNone(message)
        self.assertIsNotNone(message)
        self.assertNotEqual('', message.id)
        self.assertEqual('message1', message.content)
        self.assertNotEqual('', message.pop_receipt)
        self.assertEqual(1, message.dequeue_count)

        self.assertIsInstance(message.inserted_on, datetime)
        self.assertIsInstance(message.expires_on, datetime)
        self.assertIsInstance(message.next_visible_on, datetime)

    @QueuePreparer()
    def test_receive_one_message(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        self.assertIsNone(queue_client.receive_message())

        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')

        message1 = queue_client.receive_message()
        message2 = queue_client.receive_message()
        peeked_message3 = queue_client.peek_messages()[0]

        # Asserts
        self.assertIsNotNone(message1)
        self.assertNotEqual('', message1.id)
        self.assertEqual('message1', message1.content)
        self.assertNotEqual('', message1.pop_receipt)
        self.assertEqual(1, message1.dequeue_count)

        self.assertIsNotNone(message2)
        self.assertNotEqual('', message2.id)
        self.assertEqual('message2', message2.content)
        self.assertNotEqual('', message2.pop_receipt)
        self.assertEqual(1, message2.dequeue_count)

        self.assertEqual('message3', peeked_message3.content)
        self.assertEqual(0, peeked_message3.dequeue_count)

    @QueuePreparer()
    def test_get_messages_with_options(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        pager = queue_client.receive_messages(messages_per_page=4, visibility_timeout=20)
        result = list(pager)

        # Asserts
        self.assertIsNotNone(result)
        self.assertEqual(4, len(result))

        for message in result:
            self.assertIsNotNone(message)
            self.assertNotEqual('', message.id)
            self.assertNotEqual('', message.content)
            self.assertNotEqual('', message.pop_receipt)
            self.assertEqual(1, message.dequeue_count)
            self.assertNotEqual('', message.inserted_on)
            self.assertNotEqual('', message.expires_on)
            self.assertNotEqual('', message.next_visible_on)

    @QueuePreparer()
    def test_get_messages_with_max_messages(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        queue_client.send_message('message5')
        queue_client.send_message('message6')
        queue_client.send_message('message7')
        queue_client.send_message('message8')
        queue_client.send_message('message9')
        queue_client.send_message('message10')
        pager = queue_client.receive_messages(max_messages=5)
        result = list(pager)

        # Asserts
        self.assertIsNotNone(result)
        self.assertEqual(5, len(result))

        for message in result:
            self.assertIsNotNone(message)
            self.assertNotEqual('', message.id)
            self.assertNotEqual('', message.content)
            self.assertNotEqual('', message.pop_receipt)
            self.assertEqual(1, message.dequeue_count)
            self.assertNotEqual('', message.inserted_on)
            self.assertNotEqual('', message.expires_on)
            self.assertNotEqual('', message.next_visible_on)

    @QueuePreparer()
    def test_get_messages_with_too_little_messages(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        queue_client.send_message('message5')
        pager = queue_client.receive_messages(max_messages=10)
        result = list(pager)

        # Asserts
        self.assertIsNotNone(result)
        self.assertEqual(5, len(result))

        for message in result:
            self.assertIsNotNone(message)
            self.assertNotEqual('', message.id)
            self.assertNotEqual('', message.content)
            self.assertNotEqual('', message.pop_receipt)
            self.assertEqual(1, message.dequeue_count)
            self.assertNotEqual('', message.inserted_on)
            self.assertNotEqual('', message.expires_on)
            self.assertNotEqual('', message.next_visible_on)

    @QueuePreparer()
    def test_get_messages_with_page_bigger_than_max(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        queue_client.send_message('message5')

        # Asserts
        with self.assertRaises(ValueError):
            queue_client.receive_messages(messages_per_page=5, max_messages=2)

    @QueuePreparer()
    def test_get_messages_with_remainder(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        queue_client.send_message('message5')
        queue_client.send_message('message6')
        queue_client.send_message('message7')
        queue_client.send_message('message8')
        queue_client.send_message('message9')
        queue_client.send_message('message10')
        queue_client.send_message('message11')
        queue_client.send_message('message12')

        pager = queue_client.receive_messages(messages_per_page=3, max_messages=10)
        result = list(pager)

        remainder = queue_client.receive_messages()
        remainder_list = list(remainder)

        # Asserts
        self.assertIsNotNone(result)
        self.assertEqual(10, len(result))

        self.assertIsNotNone(remainder_list)
        self.assertEqual(2, len(remainder_list))

        for message in result:
            self.assertIsNotNone(message)
            self.assertNotEqual('', message.id)
            self.assertNotEqual('', message.content)
            self.assertNotEqual('', message.pop_receipt)
            self.assertEqual(1, message.dequeue_count)
            self.assertNotEqual('', message.inserted_on)
            self.assertNotEqual('', message.expires_on)
            self.assertNotEqual('', message.next_visible_on)

        for message in remainder_list:
            self.assertIsNotNone(message)
            self.assertNotEqual('', message.id)
            self.assertNotEqual('', message.content)
            self.assertNotEqual('', message.pop_receipt)
            self.assertEqual(1, message.dequeue_count)
            self.assertNotEqual('', message.inserted_on)
            self.assertNotEqual('', message.expires_on)
            self.assertNotEqual('', message.next_visible_on)

    @QueuePreparer()
    def test_peek_messages(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        result = queue_client.peek_messages()

        # Asserts
        self.assertIsNotNone(result)
        self.assertEqual(1, len(result))
        message = result[0]
        self.assertIsNotNone(message)
        self.assertNotEqual('', message.id)
        self.assertNotEqual('', message.content)
        self.assertIsNone(message.pop_receipt)
        self.assertEqual(0, message.dequeue_count)
        self.assertNotEqual('', message.inserted_on)
        self.assertNotEqual('', message.expires_on)
        self.assertIsNone(message.next_visible_on)

    @QueuePreparer()
    def test_peek_messages_with_options(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        result = queue_client.peek_messages(max_messages=4)

        # Asserts
        self.assertIsNotNone(result)
        self.assertEqual(4, len(result))
        for message in result:
            self.assertIsNotNone(message)
            self.assertNotEqual('', message.id)
            self.assertNotEqual('', message.content)
            self.assertIsNone(message.pop_receipt)
            self.assertEqual(0, message.dequeue_count)
            self.assertNotEqual('', message.inserted_on)
            self.assertNotEqual('', message.expires_on)
            self.assertIsNone(message.next_visible_on)

    @QueuePreparer()
    def test_clear_messages(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        queue_client.clear_messages()
        result = queue_client.peek_messages()

        # Asserts
        self.assertIsNotNone(result)
        self.assertEqual(0, len(result))

    @QueuePreparer()
    def test_delete_message(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        queue_client.send_message('message2')
        queue_client.send_message('message3')
        queue_client.send_message('message4')
        message = next(queue_client.receive_messages())
        queue_client.delete_message(message)

        messages_pager = queue_client.receive_messages(messages_per_page=32)
        messages = list(messages_pager)

        # Asserts
        assert messages is not None
        assert len(messages) == 3

    @QueuePreparer()
    def test_update_message(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        messages = queue_client.receive_messages()
        list_result1 = next(messages)
        message = queue_client.update_message(
            list_result1.id,
            pop_receipt=list_result1.pop_receipt,
            visibility_timeout=0)
        list_result2 = next(messages)

        # Asserts
        # Update response
        self.assertIsNotNone(message)
        self.assertIsNotNone(message.pop_receipt)
        self.assertIsNotNone(message.next_visible_on)
        self.assertIsInstance(message.next_visible_on, datetime)

        # Get response
        self.assertIsNotNone(list_result2)
        message = list_result2
        self.assertIsNotNone(message)
        self.assertEqual(list_result1.id, message.id)
        self.assertEqual('message1', message.content)
        self.assertEqual(2, message.dequeue_count)
        self.assertIsNotNone(message.pop_receipt)
        self.assertIsNotNone(message.inserted_on)
        self.assertIsNotNone(message.expires_on)
        self.assertIsNotNone(message.next_visible_on)

    @QueuePreparer()
    def test_update_message_content(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')

        messages = queue_client.receive_messages()
        list_result1 = next(messages)
        message = queue_client.update_message(
            list_result1.id,
            pop_receipt=list_result1.pop_receipt,
            visibility_timeout=0,
            content='new text')
        list_result2 = next(messages)

        # Asserts
        # Update response
        self.assertIsNotNone(message)
        self.assertIsNotNone(message.pop_receipt)
        self.assertIsNotNone(message.next_visible_on)
        self.assertIsInstance(message.next_visible_on, datetime)
        self.assertEqual('new text', message.content)

        # Get response
        self.assertIsNotNone(list_result2)
        message = list_result2
        self.assertIsNotNone(message)
        self.assertEqual(list_result1.id, message.id)
        self.assertEqual('new text', message.content)
        self.assertEqual(2, message.dequeue_count)
        self.assertIsNotNone(message.pop_receipt)
        self.assertIsNotNone(message.inserted_on)
        self.assertIsNotNone(message.expires_on)
        self.assertIsNotNone(message.next_visible_on)

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_account_sas(self, storage_account_name, storage_account_key):
        # SAS URL is calculated from storage key, so this test runs live only

        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        token = generate_account_sas(
            qsc.account_name,
            qsc.credential.account_key,
            ResourceTypes(object=True),
            AccountSasPermissions(read=True),
            datetime.utcnow() + timedelta(hours=1),
            datetime.utcnow() - timedelta(minutes=5)
        )

        # Act
        for credential in [token, AzureSasCredential(token)]:
            service = QueueServiceClient(
                account_url=qsc.url,
                credential=credential,
            )
            new_queue_client = service.get_queue_client(queue_client.queue_name)
            result = new_queue_client.peek_messages()

            # Assert
            self.assertIsNotNone(result)
            self.assertEqual(1, len(result))
            message = result[0]
            self.assertIsNotNone(message)
            self.assertNotEqual('', message.id)
            self.assertEqual('message1', message.content)

    @QueuePreparer()
    def test_azure_named_key_credential_access(self, storage_account_name, storage_account_key):

        # Arrange
        named_key = AzureNamedKeyCredential(storage_account_name, storage_account_key)
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), named_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')

        # Act
        result = queue_client.peek_messages()

        # Assert
        self.assertIsNotNone(result)

    @QueuePreparer()
    def test_account_sas_raises_if_sas_already_in_uri(self, storage_account_name, storage_account_key):
        with self.assertRaises(ValueError):
            QueueServiceClient(
                self.account_url(storage_account_name, "queue") + "?sig=foo",
                credential=AzureSasCredential("?foo=bar"))

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_token_credential(self, storage_account_name, storage_account_key):
        token_credential = self.generate_oauth_token()

        # Action 1: make sure token works
        service = QueueServiceClient(self.account_url(storage_account_name, "queue"), credential=token_credential)
        queues = service.get_service_properties()
        self.assertIsNotNone(queues)

        # Action 2: change token value to make request fail
        fake_credential = self.generate_fake_token()
        service = QueueServiceClient(self.account_url(storage_account_name, "queue"), credential=fake_credential)
        with self.assertRaises(ClientAuthenticationError):
            list(service.list_queues())

        # Action 3: update token to make it working again
        service = QueueServiceClient(self.account_url(storage_account_name, "queue"), credential=token_credential)
        queues = list(service.list_queues())
        self.assertIsNotNone(queues)

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_sas_read(self, storage_account_name, storage_account_key):
        # SAS URL is calculated from storage key, so this test runs live only

        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        token = generate_queue_sas(
            queue_client.account_name,
            queue_client.queue_name,
            queue_client.credential.account_key,
            QueueSasPermissions(read=True),
            datetime.utcnow() + timedelta(hours=1),
            datetime.utcnow() - timedelta(minutes=5)
        )

        # Act
        service = QueueClient.from_queue_url(
            queue_url=queue_client.url,
            credential=token,
        )
        result = service.peek_messages()

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(1, len(result))
        message = result[0]
        self.assertIsNotNone(message)
        self.assertNotEqual('', message.id)
        self.assertEqual('message1', message.content)

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_sas_add(self, storage_account_name, storage_account_key):
        # SAS URL is calculated from storage key, so this test runs live only

        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        token = generate_queue_sas(
            queue_client.account_name,
            queue_client.queue_name,
            queue_client.credential.account_key,
            QueueSasPermissions(add=True),
            datetime.utcnow() + timedelta(hours=1),
        )

        # Act
        service = QueueClient.from_queue_url(
            queue_url=queue_client.url,
            credential=token,
        )
        result = service.send_message('addedmessage')

        # Assert
        result = next(queue_client.receive_messages())
        self.assertEqual('addedmessage', result.content)

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_sas_update(self, storage_account_name, storage_account_key):
        # SAS URL is calculated from storage key, so this test runs live only

        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        token = generate_queue_sas(
            queue_client.account_name,
            queue_client.queue_name,
            queue_client.credential.account_key,
            QueueSasPermissions(update=True),
            datetime.utcnow() + timedelta(hours=1),
        )
        messages = queue_client.receive_messages()
        result = next(messages)

        # Act
        service = QueueClient.from_queue_url(
            queue_url=queue_client.url,
            credential=token,
        )
        service.update_message(
            result.id,
            pop_receipt=result.pop_receipt,
            visibility_timeout=0,
            content='updatedmessage1',
        )

        # Assert
        result = next(messages)
        self.assertEqual('updatedmessage1', result.content)

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_sas_process(self, storage_account_name, storage_account_key):
        # SAS URL is calculated from storage key, so this test runs live only

        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        token = generate_queue_sas(
            queue_client.account_name,
            queue_client.queue_name,
            queue_client.credential.account_key,
            QueueSasPermissions(process=True),
            datetime.utcnow() + timedelta(hours=1),
        )

        # Act
        service = QueueClient.from_queue_url(
            queue_url=queue_client.url,
            credential=token,
        )
        message = next(service.receive_messages())

        # Assert
        self.assertIsNotNone(message)
        self.assertNotEqual('', message.id)
        self.assertEqual('message1', message.content)

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_sas_signed_identifier(self, storage_account_name, storage_account_key):
        # SAS URL is calculated from storage key, so this test runs live only

        # Arrange
        access_policy = AccessPolicy()
        access_policy.start = datetime.utcnow() - timedelta(hours=1)
        access_policy.expiry = datetime.utcnow() + timedelta(hours=1)
        access_policy.permission = QueueSasPermissions(read=True)

        identifiers = {'testid': access_policy}

        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        resp = queue_client.set_queue_access_policy(identifiers)

        queue_client.send_message('message1')

        token = generate_queue_sas(
            queue_client.account_name,
            queue_client.queue_name,
            queue_client.credential.account_key,
            policy_id='testid'
        )

        # Act
        service = QueueClient.from_queue_url(
            queue_url=queue_client.url,
            credential=token,
        )
        result = service.peek_messages()

        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(1, len(result))
        message = result[0]
        self.assertIsNotNone(message)
        self.assertNotEqual('', message.id)
        self.assertEqual('message1', message.content)

    @QueuePreparer()
    def test_get_queue_acl(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()

        # Act
        acl = queue_client.get_queue_access_policy()

        # Assert
        self.assertIsNotNone(acl)
        self.assertEqual(len(acl), 0)

    @QueuePreparer()
    def test_get_queue_acl_iter(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()

        # Act
        acl = queue_client.get_queue_access_policy()
        for signed_identifier in acl:
            pass

        # Assert
        self.assertIsNotNone(acl)
        self.assertEqual(len(acl), 0)

    @QueuePreparer()
    def test_get_queue_acl_with_non_existing_queue(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)

        # Act
        with self.assertRaises(ResourceNotFoundError):
            queue_client.get_queue_access_policy()

            # Assert

    @QueuePreparer()
    def test_set_queue_acl(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()

        # Act
        resp = queue_client.set_queue_access_policy(signed_identifiers=dict())

        # Assert
        self.assertIsNone(resp)
        acl = queue_client.get_queue_access_policy()
        self.assertIsNotNone(acl)

    @QueuePreparer()
    def test_set_queue_acl_with_empty_signed_identifiers(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()

        # Act
        queue_client.set_queue_access_policy(signed_identifiers={})

        # Assert
        acl = queue_client.get_queue_access_policy()
        self.assertIsNotNone(acl)
        self.assertEqual(len(acl), 0)

    @QueuePreparer()
    def test_set_queue_acl_with_empty_signed_identifier(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()

        # Act
        queue_client.set_queue_access_policy(signed_identifiers={'empty': None})

        # Assert
        acl = queue_client.get_queue_access_policy()
        self.assertIsNotNone(acl)
        self.assertEqual(len(acl), 1)
        self.assertIsNotNone(acl['empty'])
        self.assertIsNone(acl['empty'].permission)
        self.assertIsNone(acl['empty'].expiry)
        self.assertIsNone(acl['empty'].start)

    @QueuePreparer()
    def test_set_queue_acl_with_signed_identifiers(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()

        # Act
        access_policy = AccessPolicy(permission=QueueSasPermissions(read=True),
                                     expiry=datetime.utcnow() + timedelta(hours=1),
                                     start=datetime.utcnow() - timedelta(minutes=5))
        identifiers = {'testid': access_policy}

        resp = queue_client.set_queue_access_policy(signed_identifiers=identifiers)

        # Assert
        self.assertIsNone(resp)
        acl = queue_client.get_queue_access_policy()
        self.assertIsNotNone(acl)
        self.assertEqual(len(acl), 1)
        self.assertTrue('testid' in acl)

    @QueuePreparer()
    def test_set_queue_acl_too_many_ids(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()

        # Act
        identifiers = dict()
        for i in range(0, 16):
            identifiers[f'id{i}'] = AccessPolicy()

        # Assert
        with self.assertRaises(ValueError):
            queue_client.set_queue_access_policy(identifiers)

    @QueuePreparer()
    def test_set_queue_acl_with_non_existing_queue(self, storage_account_name, storage_account_key):
        # Arrange
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)

        # Act
        with self.assertRaises(ResourceNotFoundError):
            queue_client.set_queue_access_policy(signed_identifiers=dict())

            # Assert

    @QueuePreparer()
    def test_unicode_create_queue_unicode_name(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_name = '啊齄丂狛狜'

        with self.assertRaises(HttpResponseError):
            # not supported - queue name must be alphanumeric, lowercase
            client = qsc.get_queue_client(queue_name)
            client.create_queue()

            # Asserts

    @QueuePreparer()
    def test_unicode_get_messages_unicode_data(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1㚈')
        message = next(queue_client.receive_messages())

        # Asserts
        self.assertIsNotNone(message)
        self.assertNotEqual('', message.id)
        self.assertEqual('message1㚈', message.content)
        self.assertNotEqual('', message.pop_receipt)
        self.assertEqual(1, message.dequeue_count)
        self.assertIsInstance(message.inserted_on, datetime)
        self.assertIsInstance(message.expires_on, datetime)
        self.assertIsInstance(message.next_visible_on, datetime)

    @QueuePreparer()
    def test_unicode_update_message_unicode_data(self, storage_account_name, storage_account_key):
        # Action
        qsc = QueueServiceClient(self.account_url(storage_account_name, "queue"), storage_account_key)
        queue_client = self._get_queue_reference(qsc)
        queue_client.create_queue()
        queue_client.send_message('message1')
        messages = queue_client.receive_messages()

        list_result1 = next(messages)
        list_result1.content = '啊齄丂狛狜'
        queue_client.update_message(list_result1, visibility_timeout=0)

        # Asserts
        message = next(messages)
        self.assertIsNotNone(message)
        self.assertEqual(list_result1.id, message.id)
        self.assertEqual('啊齄丂狛狜', message.content)
        self.assertNotEqual('', message.pop_receipt)
        self.assertEqual(2, message.dequeue_count)
        self.assertIsInstance(message.inserted_on, datetime)
        self.assertIsInstance(message.expires_on, datetime)
        self.assertIsInstance(message.next_visible_on, datetime)

    @pytest.mark.live_test_only
    @QueuePreparer()
    def test_transport_closed_only_once(self, storage_account_name, storage_account_key):
        transport = RequestsTransport()
        prefix = TEST_QUEUE_PREFIX
        queue_name = self.get_resource_name(prefix)
        with QueueServiceClient(
            self.account_url(storage_account_name, "queue"),
            credential=storage_account_key, transport=transport) as qsc:
            qsc.get_service_properties()
            assert transport.session is not None
            with qsc.get_queue_client(queue_name) as qc:
                assert transport.session is not None
            qsc.get_service_properties()
            assert transport.session is not None

# ------------------------------------------------------------------------------
if __name__ == '__main__':
    unittest.main()
