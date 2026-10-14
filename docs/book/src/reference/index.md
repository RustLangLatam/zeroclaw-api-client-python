# Reference

- [Endpoint map](./endpoints.md): every gateway route the client calls, and
  the method that calls it.
- [Compatibility](./compatibility.md): the ZeroClaw builds the client is
  verified against, and what differs between them.

The API documentation of each class and method is in its docstring (Google
style), which editors show on hover; locally,
`python -m pydoc zeroclaw_client.Client` prints it. The package ships
`py.typed`, so type checkers read its annotations as they are.
