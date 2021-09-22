# Introduction

This project is a service deployed "at the edge" that polls for messages from a
mediator and forwards/relays the messages to an agent service that does not
support polling for messages from a mediator.

# Context

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

# System Architecture

## Alice and Bob (Alice domain simplified)

![](assets/proxy-mediator-0.png)

## Alice and Bob (Alice domain depicted)

![](assets/proxy-mediator-1.png)

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
- Implement an Admin API to control the proxy mediator (perhaps with the
  exception of retrieving an invite as this is helpful in automating setup).

# Assumptions

To simplify a first pass at this mediation service, we will make the following
assumptions:

- The proxy mediator services exactly one agent.
- The proxy mediator implements only the connection and coordinate mediation
  protocols (maybe discover features, pickup protocols).
    - Or would it be better to use DID Exchange protocol?
- The proxy mediator will automatically accept mediation requests.
- The proxy mediator will more or less ignore keylist updates and assume
  everything it receives can be passed on to the agent.
- The proxy mediator will hold no more state than is absolutely necessary:
    - Mediator connection info (once set)
    - Agent connection info (once set)
- The proxy mediator may reuse it's verkey with the mediator as the routing key
  reported to the agent.
