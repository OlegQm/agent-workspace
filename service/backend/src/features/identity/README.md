# Identity Feature

## Purpose

Authenticate accounts and provide scoped regular/admin dependencies.
Persist opaque login sessions; do not derive authority from a username or frontend state.

## Responsibilities

- Validate login credentials and create/revoke hashed server sessions.
- Refresh expiry with throttled database writes.
- Present safe account data and enforce regular/admin endpoint roles.

## Entry Points

- [Auth endpoints](api/router.py)
- [User/role/database dependencies](api/dependencies.py)
- [AuthenticationService](application/authentication.py)
- [Session cookie handling](api/cookies.py)

## Dependencies and Boundaries

Account/session mappings are shared database infrastructure. Identity does not own
conversation persistence. HttpOnly cookie transport and settings validators cooperate
with bootstrap origin checks; a role check is still required at each protected route.

## Tests

`tests/features/identity` covers service behavior, dependencies, cookies, schemas,
presenters, and routes. Composition tests cover unauthorized UI/API flows. Use fake
passwords and disposable session records.

## Related Documentation

- [Authorization boundaries](../../../../../docs/security.md)
- [Conversation ownership](../chat/README.md)
- [Backend map](../../../README.md)
- [Architecture](../../../../../docs/architecture.md)
