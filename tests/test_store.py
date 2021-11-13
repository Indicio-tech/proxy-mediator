import pytest
import json

from proxy_mediator.agent import Connection
from proxy_mediator.store import Store
from aries_staticagent.connection import Target


@pytest.fixture
def connection():
    """Create a Connection"""
    target_conn = Connection.random()
    conn = Connection.random(
        target=Target(their_vk=target_conn.verkey_b58, endpoint="http://example.com")
    )
    conn.state = "state"
    conn.multiuse = False
    conn.invitation_key = "invitation_key"
    return conn


@pytest.fixture(scope="session")
def store(tmpdir_factory):
    """Store with a temporary sqlite file as backend. This is used to test reopening."""
    yield Store("sqlite://" + str(tmpdir_factory.mktemp("data").join("db")), "testing")


@pytest.mark.asyncio
async def test_serialization(connection):
    """Test serialization method from Connection object
    to json object"""
    serialized = Store.serialize_json(connection)
    assert isinstance(serialized, str)


@pytest.mark.asyncio
async def test_deserialization():
    """Test deserialization method from json object
    to Connection object"""
    json_obj = json.dumps(
        {
            "state": "E2Vfkfn",
            "multiuse": "KJtQkEuo4Pn",
            "invitation_key": "fm6KT2siLJ5ZVyXoAcx",
            "did": "PygexhzBXqUK4EWLPpUxaR",
            "verkey": "DXMm23n2oKKXHfpUbrYH98KvfGvJbmRfQcT7pXpHiFo7",
            "sigkey": "5HEn361K7SbL5iZGQpAhkrwTTxUDZ6mSS4WvSKmbRttqSDFtFuiEXHz3PJ2x",
            "recipients": ["FdPjv5vuxjChhWPKEDLV3tgGQjt57cBtX5GCcvGvuRw8"],
            "endpoint": "http://example.com",
        }
    )
    deserialized = Store.deserialize_json(json_obj)
    assert isinstance(deserialized, Connection)


@pytest.mark.parametrize("entity", [Store.Name.agent, Store.Name.mediator])
@pytest.mark.asyncio
async def test_store_retrieve_connection(entity, store: Store, connection: Connection):
    """Parametrized test method for storing and retrieving
    agent and mediator connections"""
    async with store:
        await store.store_connection(connection, entity)

    async with store:
        retrieved_conn = await store.retrieve_connection(entity)

    assert retrieved_conn
    assert connection.state == retrieved_conn.state
    assert connection.multiuse == retrieved_conn.multiuse
    assert connection.invitation_key == retrieved_conn.invitation_key
    assert connection.did == retrieved_conn.did
    assert connection.verkey == retrieved_conn.verkey
    assert connection.verkey_b58 == retrieved_conn.verkey_b58
    assert connection.sigkey == retrieved_conn.sigkey
    assert connection.target and retrieved_conn.target
    assert connection.target.recipients == retrieved_conn.target.recipients
    assert connection.target.endpoint == retrieved_conn.target.endpoint
