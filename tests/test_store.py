import pytest

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
    serialized = Connection.to_store(connection)
    assert isinstance(serialized, str)


@pytest.mark.asyncio
async def test_deserialization():
    """Test deserialization method from json object
    to Connection object"""
    json_obj = {
        "state": "E2Vfkfn",
        "multiuse": "KJtQkEuo4Pn",
        "invitation_key": "fm6KT2siLJ5ZVyXoAcx",
        "did": "PygexhzBXqUK4EWLPpUxaR",
        "verkey": "DXMm23n2oKKXHfpUbrYH98KvfGvJbmRfQcT7pXpHiFo7",
        "sigkey": "5HEn361K7SbL5iZGQpAhkrwTTxUDZ6mSS4WvSKmbRttqSDFtFuiEXHz3PJ2x",
        "recipients": ["FdPjv5vuxjChhWPKEDLV3tgGQjt57cBtX5GCcvGvuRw8"],
        "endpoint": "http://example.com",
        "diddoc": {
            "@context": "https://w3id.org/did/v1",
            "id": "123456789",
            "publicKey": [
                {
                    "id": "123456789" + "#keys-1",
                    "type": "Ed25519VerificationKey2018",
                    "controller": "123456789",
                    "publicKeyBase58": "123456789",
                }
            ],
            "service": [
                {
                    "id": "123456789" + "#indy",
                    "type": "IndyAgent",
                    "recipientKeys": ["123456789"],
                    "routingKeys": [],
                    "serviceEndpoint": "ws://agents-r-us.org/ws",
                }
            ],
        },
    }
    deserialized = Connection.from_store(json_obj)
    assert isinstance(deserialized, Connection)


@pytest.mark.asyncio
async def test_store_retrieve_connections(store: Store, connection: Connection):
    """Parametrized test method for storing and retrieving
    agent and mediator connections"""
    async with store:
        async with store.session() as session:
            await store.store_connection(session, connection)

    async with store:
        async with store.session() as session:
            entry, *_ = await store.retrieve_connections(session)
            retrieved_conn = Connection.from_store(entry.value_json)

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


@pytest.mark.asyncio
async def test_store_retrieve_agent(store: Store, connection: Connection):
    async with store:
        async with store.session() as session:
            await store.store_agent(session, connection.verkey_b58)

        async with store.session() as session:
            retrieved = await store.retrieve_agent(session)

        assert retrieved == connection.verkey_b58


@pytest.mark.asyncio
async def test_store_retrieve_mediator(store: Store, connection: Connection):
    async with store:
        async with store.session() as session:
            await store.store_mediator(session, connection.verkey_b58)

        async with store.session() as session:
            retrieved = await store.retrieve_mediator(session)

        assert retrieved == connection.verkey_b58
