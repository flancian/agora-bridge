# Agora Bridge Repository API

This is a part of Agora Bridge that aims to do the following:

- Add a new user-owned repository to the Agora repository list. This is meant to be used as part of the signup flow.
- Attach a new resource (e.g. a note, passed in full) to a node. 
    - This resource is stored in an Agora managed git repository for the user. 
    - The intent here is to store and serve nodes for users in repositories they can optionally fork and take over (moving to a non-managed setup like the one supported primarily by the Agora).
- Serve managed git repositories. This is intended for use by both the Agora (which will treat these as any other git source) and users that want to fork the managed repositories.

Code is Typescript/Node. Use `./run-prod.sh` to run. Status: alpha.

## Testing

Here are some example curl invocations to interact with the API. Reach out if you need a hand!

Add a note `test.md` in the managed repository, with content `test content`:

```
curl -H 'Content-Type: application/json' -X PUT -d '{"name":  "test", "content": "test content"}' localhost:3141/node 
```
