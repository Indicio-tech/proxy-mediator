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


Clone the Proxy Mediator:
```sh
$ git clone https://github.com/Indicio-tech/proxy-mediator.git
```

## To run the demo setup:
  - `docker-compose up --build`


## Services started by the above command:
- **Proxy**: The mediator inside the firewall which connects to the external mediator.
  - The proxy mediator polls for messages continuously via websocket while the websocket connection is open.
- **Agent**: The agent that is sending and receiving messages through the mediators.
- **Mediator-tunnel**: The tunnel that creates an endpoint for the external mediator which can be used with agents including mobile agents and agents outside the computer's network.
- **Reverse-proxy**: The service that redirects traffic from one endpoint to another.
- **Mediator**: The external mediator that connects to the internal mediator from outside of the firewall.
- **Setup**: Builds the context and sets the environment variables.



# Setup

Steps to set up a connection to the mediators:
1. Retrieve the invitation from the external mediator
    - Create an invitation request for the external mediator and return the invitation URL.
2. Receive the external mediator's invitation on the proxy mediator
    - Make an HTTP post request to the `receive_mediator_invitation` endpoint, passing in the external mediator invitation, to allow the proxy mediator to receive this invitation. (The Admin API offers the same functionality.) The proxy mediator and external mediator are now connected.
3. Retrieve the invitation from the proxy mediator
    - Make an HTTP get request to the `retrieve_agent_invitation` endpoint to retrieve the invitation from the proxy mediator to be sent to the agent.
4. Receive the proxy mediator's invitation on the agent
    - Verify that the state of the connection record is `active`; otherwise, retrieve connection records on the agent until the correct record is found. If the correct record is found, the proxy mediator and the agent are now connected.
5. Request mediation from the proxy mediator
    - The agent requests mediation from the proxy mediator. Verify that the state of the mediation record is `granted`; otherwise retrieve mediation requests by `mediation_id` until the correct record is found. If the correct record is found, the proxy has now granted mediation to the agent.
6. Set proxy as default mediator
    - The proxy mediator is now the default mediator for the agent.

This setup is implemented in `docker/setup/main.py` and `int/tests/conftest.py`. These scripts can be used directly or adapted to meet your needs.


# System Architecture

## Alice and Bob (Alice domain simplified)

![](assets/proxy-mediator-0.png)

## Alice and Bob (Alice domain depicted)

![](assets/proxy-mediator-1.png)

The proxy mediator uses an Aries Askar store for secure connection persistence.

# Goals 

- Create a functional mechanism for running cloud agents behind a firewall.
- The connected cloud agent treats the proxy mediator exactly as it would a
  normal mediator.
- Proxy mediator persists configuration across restarts.
- Proxy mediator is configured through command line arguments or environment
  variables.
- Package as container and python package.
- Simple and fast to implement.

# Non-Goals

- Create a full mediator solution.
- Implement an Admin API to control the proxy mediator (perhaps with the exception of retrieving an invite as this is helpful in automating setup).
- Develop a robust message queue, as this will be used primarily by agents that cannot retrieve from a queue anyway.


# Simplifications

To simplify a first pass at this mediation service, we will make the following simplifications:

- The proxy mediator services exactly one agent.
- The proxy mediator implements only the connection and coordinate mediation protocols (potentially discover features, pickup protocols).
- The proxy mediator will automatically accept mediation requests.
- The proxy mediator will more or less ignore keylist updates and assume
  everything it receives can be passed on to the agent.
- The proxy mediator will hold no more state than is absolutely necessary:
    - Mediator connection info (once set)
    - Agent connection info (once set)
- The proxy mediator may reuse its verkey with the mediator as the routing key reported to the agent.