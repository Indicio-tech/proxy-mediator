# Proxy Mediator Setup Utility

This service automates the setup of a proxy mediator at a connected agent. The
basic steps it follows are:

1. Retrieve invitation from mediator or from the `MEDIATOR_INVITE` environment
   variable.
2. Instruct proxy to receive mediator invitation.
3. Retrieve invitation from proxy.
4. Instruct agent to receive proxy invitation.
5. Instruct agent to request mediation from proxy.
6. Instruct agent to set proxy as default mediator.

## Configuration

Configuration is done through the following environment variables:

- `PROXY` - URL to proxy mediator.
- `AGENT` - URL to Admin API of agent.
- `MEDIATOR` - Optional. URL to Admin API of mediator. Can be used to actively
	retrieve an invitation from a mediator to which we have Admin API access.
	Either this variable or `MEDIATOR_INVITE` must be set.
- `MEDIATOR_INVITE` - Optional. Connection invitation to external mediator.
	Either this variable or `MEDIATOR` must be set.
- `WAIT_HOSTS` - Comma separated ist of hosts to wait for before beginning
  setup. Ex. `agent:3000,proxy:3000`.
