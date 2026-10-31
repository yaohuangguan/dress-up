# JavaScript and TypeScript tests

Complete example: `examples/javascript/app-test.mjs`. Run it with
`node examples/javascript/app-test.mjs` on Node 24 or later.

Use the project's framework if it has one, such as Vitest, Jest or `node:test`. The
patterns stay the same.

## Strict network stub

```js
const original = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = new URL(String(input));
  assert.equal(url.origin, "https://api.provider.test");
  assert.equal(init?.method ?? "GET", "GET", "Unexpected provider write " + url.pathname);
  const response = responses[url.pathname + url.search];
  assert(response, "Unexpected provider call " + url.pathname + url.search);
  return Response.json(response);
};
try {
  // run the test
} finally {
  globalThis.fetch = original;
}
```

## Error helper

```js
const expectError = async (response, status, error) => {
  const result = await response;
  assert.equal(result.status, status);
  assert.equal((await result.json()).error, error);
};
```

## Concurrency

```js
const results = await Promise.all(Array.from({ length: 6 }, () => deliver("evt_1")));
assert(results.every((result) => result.status === 200));
assert.equal(balance(), 500, "Concurrent deliveries grant the credit once");
```

## Browser tests

- Fail any test on an uncaught page error.
- Block every origin except the local app.
- Build route lists from the app's own route definitions.
- Query by role and visible text, not by CSS structure.
- Cover desktop and mobile, and each supported language and theme.
- Set retries to 0 in CI and forbid `.only`.

## Mistakes to avoid

- A missing `await` makes a rejected assertion pass silently.
- `toBeTruthy()` passes for almost anything. Use `toBe` or `toEqual`.
- `vi.mock` or `jest.mock` on your own module tests the mock.
- A global left replaced after a failure affects later tests. Restore in `finally`.
