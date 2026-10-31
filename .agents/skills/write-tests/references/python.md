# Python tests

Complete example: `examples/python/test_app.py`. Run it from that folder with
`python -m unittest`.

The example uses the standard library so that it runs anywhere. Use `pytest` if
the project does. The patterns stay the same.

## Strict fake at the boundary

Pass the external client in, so the test does not need to patch your own modules:

```python
def fetch_event(event_id):
    self.assertIn(event_id, self.events, "Unexpected provider call " + event_id)
    return self.events[event_id]

app = App(db, fetch_event)
```

## Real database

```python
db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("PRAGMA foreign_keys=ON")
db.executescript(Path(__file__).with_name("schema.sql").read_text())
```

If production uses PostgreSQL or MySQL and the code relies on its behaviour, use
that database in a container or the project's test instance.

## Concurrency

```python
with ThreadPoolExecutor(max_workers=6) as pool:
    results = list(pool.map(lambda _: deliver("evt_paid"), range(6)))
self.assertTrue(all(status == 200 for status, _ in results))
self.assertEqual(self.credits(), 500, "Concurrent deliveries grant the credit once")
```

## Mistakes to avoid

- `assertTrue(result)` passes for almost anything. Use `assertEqual`.
- `Mock()` accepts any call, including a misspelled method. Use `create_autospec`
  if you must mock.
- `patch` must target the name where it is used, not where it is defined.
- Mutable state shared at class level leaks between tests. Build it in `setUp`.
