"""Connections Protocol Starter Kit"""
import argparse
import json
import os
import sys
from aiohttp import web

from aries_staticagent import (
    StaticConnection,
    crypto,
    utils,
    Message
)

from connections import Connections
from connections import States as ConnectionStates


# Pull protocols directory into path
sys.path.insert(0, '../../')


def config():
    """ Get config """
    def environ_or_required(key):
        if os.environ.get(key):
            return {'default': os.environ.get(key)}
        return {'required': True}

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', **environ_or_required('PORT'))
    parser.add_argument(
        '--replace-keys',
        action='store_true',
        dest='replace'
    )
    args = parser.parse_args()
    return args


def store_connection(conn: StaticConnection):
    if hasattr(conn, 'state') and (
        conn.state.state == ConnectionStates.COMPLETE or
        conn.state.state == ConnectionStates.RESPONDED
    ):
        with open('.keys', 'w+') as key_file:
            json.dump({
                'did': crypto.bytes_to_b58(conn.my_vk[:16]),
                'my_vk': crypto.bytes_to_b58(conn.my_vk),
                'my_sk': crypto.bytes_to_b58(conn.my_sk),
                'their_vk': crypto.bytes_to_b58(conn.their_vk),
                'endpoint': conn.endpoint
            }, key_file)


def recall_connection():
    if not os.path.exists('.keys'):
        return None
    with open('.keys', 'r') as key_file:
        info = json.load(key_file)
        return StaticConnection(
            info['my_vk'],
            info['my_sk'],
            info['their_vk'],
            info['endpoint']
        )


def main():
    """Main."""
    args = config()

    connections = Connections('http://localhost:{}'.format(args.port))
    conn = recall_connection()
    if not conn or args.replace:
        conn, invitation_url = connections.create_invitation()
        print('Use this invitation to connect to the toolbox.')
        print('Invitation URL:', invitation_url)

    conn.route_module(connections)

    @conn.route('did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/basicmessage/1.0/message')
    async def basic_message_auto_responder(msg, conn):
        """Automatically respond to basicmessages."""
        await conn.send_async({
            "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/"
                     "basicmessage/1.0/message",
            "~l10n": {"locale": "en"},
            "sent_time": utils.timestamp(),
            "content": "You said: {}".format(msg['content'])
        })


    async def handle(request):
        """aiohttp handle POST."""
        response = []
        with conn.reply_handler(response.append):
            await conn.handle(await request.read())

        if response:
            return web.Response(body=response.pop())

        raise web.HTTPAccepted()

    app = web.Application()
    app.add_routes([web.post('/', handle)])

    web.run_app(app, port=args.port)
    if args.replace:
        store_connection(conn)



if __name__ == "__main__":
    main()
