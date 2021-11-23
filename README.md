# Introduction

This project is a service deployed "at the edge" that polls for messages from a
mediator and forwards/relays the messages to an agent service that does not
support polling for messages from a mediator.

The concept of Mediation makes it possible for agents to be able to reliably
receive messages even while not being directly reachable over the internet or
some other delivery mechanism. This covers a wide range of scenarios, including:

- A phone that loses service while driving through Wyoming
- A phone or other mobile device that runs out of battery
- A device that frequently switches networks and so does not have a reliable IP
  address
- A device that is connected to the internet behind a firewall

Mobile agents are well aware of these intermittent connectivity scenarios and
are architected to rely on mediation services to receive messages. Cloud agents,
on the other hand, are architected to have reliable connectivity but could
feasibly be deployed behind a firewall. These agents are not well suited to
relying on mediation services to receive messages while behind a firewall.

Rather than introducing the complexity of supporting both actively polling
messages from a mediator and being able to asynchronously receive messages over
a transport, such an agent could use a separate service that implements the
active polling and then forwards/relays the retrieved messages to it.



# Quickstart


Clone the Proxy Mediator and prepare a virtual environment:
```sh
$ git clone https://github.com/Indicio-tech/proxy-mediator.git
$ cd proxy-mediator
$ python3 -m venv env
$ source env/bin/activate
```

## To run the demo setup:
  - `docker-compose up --build`


## Services started by the above command:
- **Proxy**: The mediator inside the firewall which connects to the external mediator.
- **Agent**: The agent that is sending and receiving messages through the mediators.
- **Mediator-tunnel**: The tunnel through which the external mediator transfers information.
- **Reverse-proxy**: The service that redirects traffic from one endpoint to another.
- **Mediator**: The external mediator that connects to the internal mediator from outside of the firewall.
- **Setup**: Builds the context and sets the environment variables.

  - The MessageRetriever retrieves messages by opening a websocket connection and continuously polling for messages using a trust ping with `response_requested` set to false while the websocket connection is open.


# Setup

Steps to set up a connection to the mediators:
1. Retrieve the invitation from the external mediator
    - Use the `acapy_client` to create an invitation request for the external mediator and return the invitation url.
2. Receive the external mediator's invitation on the proxy mediator
    - Using `AsyncClient`, make an HTTP post request to allow the proxy mediator to receive the invitation from the external mediator. (The Admin API offers the same functionality.) The proxy mediator and external mediator are now connected.
3. Retrieve the invitation from the proxy mediator
    - Using `AsyncClient`, make an HTTP get request to retrieve the invitation from the proxy mediator.
4. Receive the proxy mediator's invitation on the agent
    - The proxy mediator and the agent are now connected.
5. Request mediation from the proxy mediator
    - The agent requests mediation from the proxy mediator. Proxy has now granted mediation to agent.
6. Set proxy as default mediator
    - The proxy mediator is now the default mediator for the agent.

This setup is implemented in `docker/setup/main.py` and `int/tests/conftest.py`. These steps can be used directly or in your own setup.


# System Architecture

## Alice and Bob (Alice domain simplified)

![](assets/proxy-mediator-0.png)

## Alice and Bob (Alice domain depicted)

![](assets/proxy-mediator-1.png)

The proxy mediator uses an Aries Askar store for secure connection persistence.