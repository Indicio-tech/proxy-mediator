import pytest
import json

from proxy_mediator.agent import Connection
from proxy_mediator.askar_store import AskarStore
from aries_staticagent.connection import Target


@pytest.fixture
def connection():
    """Create a Connection"""
    target_conn = Connection.random()
    conn = Connection.random(
        target=Target(their_vk=target_conn.verkey_b58, endpoint="http://example.com")
    )
    conn.recipient_key = "recipient_key"
    conn.state = "state"
    conn.multiuse = "multiuse"
    conn.invitation_key = "invitation_key"
    return conn


@pytest.mark.asyncio
async def test_serialization(connection):
    """Test serialization method from Connection object
    to json object"""
    conn = connection
    store = AskarStore()
    serialized = store.serialize_json(conn)
    assert isinstance(serialized, str) and not isinstance(serialized, Connection)


@pytest.mark.asyncio
async def test_deserialization():
    """Test deserialization method from json object
    to Connection object"""
    store = AskarStore()
    json_obj = json.dumps(
        {
            "state": "E2Vfkfn",
            "multiuse": "KJtQkEuo4Pn",
            "invitation_key": "fm6KT2siLJ5ZVyXoAcx",
            "did": "PygexhzBXqUK4EWLPpUxaR",
            "my_vk": "DXMm23n2oKKXHfpUbrYH98KvfGvJbmRfQcT7pXpHiFo7",
            "my_sk": "5HEn361K7SbL5iZGQpAhkrwTTxUDZ6mSS4WvSKmbRttqSDFtFuiEXHz3PJ2x",
            "recipients": ["FdPjv5vuxjChhWPKEDLV3tgGQjt57cBtX5GCcvGvuRw8"],
            "endpoint": "http://example.com",
        }
    )
    deserialized = store.deserialize_json(json_obj)
    assert isinstance(deserialized, Connection) and not isinstance(deserialized, str)


entities = [("agent"), ("mediator")]


@pytest.mark.parametrize("entity", entities)
@pytest.mark.asyncio
async def test_store_retrieve_connection(entity, connection):
    """Parametrized test method for storing and retrieving
    agent and mediator connections"""
    conn = connection
    store = await AskarStore.store()
    await AskarStore.store_connection(conn, store, entity)
    retrieved_conn = await AskarStore.retrieve_connection(store, entity)
    assert isinstance(retrieved_conn, Connection)
