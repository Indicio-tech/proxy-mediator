""" Protocol modules and helpers. """


class ImpossibleStateTransition(Exception):
    """When a state transition is impossible given the current state."""


class ProtocolStateMachine:
    """The state machine of a protocol."""

    transitions = {}

    def __init__(self):
        self.state = None
        self.role = None

    def transition(self, event):
        """Follow transition table for event."""
        if self.role not in self.__class__.transitions:
            raise ImpossibleStateTransition(
                "Role {} has no defined transitions.".format(self.role)
            )

        if self.state not in self.__class__.transitions[self.role]:
            raise ImpossibleStateTransition(
                "Role {} does not have state {}.".format(self.role, self.state)
            )

        if event not in self.__class__.transitions[self.role][self.state]:
            raise ImpossibleStateTransition(
                "State {} has no transitions on event {}".format(self.state, event)
            )

        self.state = self.__class__.transitions[self.role][self.state][event]
