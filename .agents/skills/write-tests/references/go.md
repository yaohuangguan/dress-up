# Go tests

Complete example: `examples/go/app_test.go`. Run it from that folder with
`go test ./...`, and add `-race` where the toolchain supports it.

## Strict fake server

```go
provider := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		t.Errorf("unexpected provider write: %s %s", r.Method, r.URL.Path)
	}
	event, ok := events[strings.TrimPrefix(r.URL.Path, "/v1/events/")]
	if !ok {
		t.Errorf("unexpected provider call: %s", r.URL.Path)
		w.WriteHeader(http.StatusNotFound)
		return
	}
	json.NewEncoder(w).Encode(event)
}))
t.Cleanup(provider.Close)
```

## Wait for an outcome

```go
// A slow host must not end the run first; this bound only catches a hang.
const settleTimeout = 60 * time.Second

deadline := time.Now().Add(settleTimeout)
for !finished() {
	if time.Now().After(deadline) {
		t.Fatalf("did not settle within %v", settleTimeout)
	}
	time.Sleep(50 * time.Millisecond)
}
```

## Helpers to use

- `t.TempDir()` for files, `t.Setenv()` for environment, `t.Cleanup()` for teardown.
- `t.Helper()` in assertion helpers, so failures point at the caller.
- `t.Run()` with a table for many inputs.
- `httptest` for HTTP boundaries.

## Mistakes to avoid

- `t.Fatal` from a goroutine other than the test's does not stop the test. Use
  `t.Error` there.
- A wait shorter than the time the product allows will flake on slow machines.
- Paths, processes and signals differ by OS. Test on each OS you ship.
- For filesystem rules, also cover symlink escapes and missing parents.
