package deviceapi

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"sync"
	"testing"
)

const secret = "canary-private-credential"

type fixture struct {
	store        *Store
	server       *httptest.Server
	providerDown bool
}

// newFixture runs the real handler over HTTP, with a strict fake provider.
func newFixture(t *testing.T) *fixture {
	t.Helper()
	f := &fixture{store: &Store{
		Sessions: map[string]string{"owner-session": "owner", "intruder-session": "intruder"},
		Devices:  map[string]*Device{"laptop": {ID: "laptop", Owner: "owner", Name: "Laptop", Credential: secret}},
		Paid:     map[string]bool{},
		Credits:  map[string]int{},
	}}
	events := map[string]providerEvent{
		"evt_paid": {Status: "paid", UserID: "owner", Credits: 500},
		"evt_open": {Status: "open", UserID: "owner", Credits: 500},
	}
	provider := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("unexpected provider write: %s %s", r.Method, r.URL.Path)
		}
		if f.providerDown {
			// The body looks paid, so only the status can reveal the failure.
			w.WriteHeader(http.StatusServiceUnavailable)
			json.NewEncoder(w).Encode(events["evt_paid"])
			return
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
	f.server = httptest.NewServer(NewHandler(f.store, provider.URL, provider.Client()))
	t.Cleanup(f.server.Close)
	return f
}

func (f *fixture) post(t *testing.T, path, body, session string) (int, string) {
	t.Helper()
	// Goroutines call this too, so it reports with t.Errorf and never t.Fatal.
	request, err := http.NewRequest(http.MethodPost, f.server.URL+path, strings.NewReader(body))
	if err != nil {
		t.Errorf("build request: %v", err)
		return 0, ""
	}
	if session != "" {
		request.AddCookie(&http.Cookie{Name: "session", Value: session})
	}
	response, err := f.server.Client().Do(request)
	if err != nil {
		t.Errorf("send request: %v", err)
		return 0, ""
	}
	defer response.Body.Close()
	text, err := io.ReadAll(response.Body)
	if err != nil {
		t.Errorf("read response: %v", err)
		return 0, ""
	}
	return response.StatusCode, string(text)
}

func (f *fixture) rename(t *testing.T, name any, session string) (int, string) {
	t.Helper()
	body, err := json.Marshal(map[string]any{"name": name})
	if err != nil {
		t.Fatal(err)
	}
	return f.post(t, "/devices/laptop/rename", string(body), session)
}

func (f *fixture) deliver(t *testing.T, id string) (int, string) {
	t.Helper()
	return f.post(t, "/webhooks/payment", `{"id":"`+id+`"}`, "")
}

func TestDeniedCallersChangeNothing(t *testing.T) {
	f := newFixture(t)
	before := *f.store.Devices["laptop"]
	for _, c := range []struct {
		session string
		status  int
		errText string
	}{
		{"", http.StatusUnauthorized, "unauthorized"},
		{"forged", http.StatusUnauthorized, "unauthorized"},
		{"intruder-session", http.StatusNotFound, "device not found"},
	} {
		status, body := f.rename(t, "Mine", c.session)
		if status != c.status || !strings.Contains(body, c.errText) {
			t.Errorf("session %q: got %d %s, want %d %s", c.session, status, body, c.status, c.errText)
		}
	}
	if *f.store.Devices["laptop"] != before {
		t.Errorf("denied calls changed the device: %+v", f.store.Devices["laptop"])
	}
	if len(f.store.Audits) != 0 {
		t.Errorf("denied calls were recorded as changes: %v", f.store.Audits)
	}
}

func TestNameMustHaveContent(t *testing.T) {
	f := newFixture(t)
	for _, name := range []any{"", "   ", 7, nil} {
		if status, _ := f.rename(t, name, "owner-session"); status != http.StatusBadRequest {
			t.Errorf("name %v: got %d, want 400", name, status)
		}
	}
}

func TestNameLimitOnBothSides(t *testing.T) {
	f := newFixture(t)
	exact, over := strings.Repeat("M", maxName), strings.Repeat("M", maxName+1)
	if _, body := f.rename(t, "  "+exact+"  ", "owner-session"); !strings.Contains(body, `"`+exact+`"`) {
		t.Errorf("a name at the limit must be kept whole: %s", body)
	}
	if status, _ := f.rename(t, over, "owner-session"); status != http.StatusOK {
		t.Errorf("got %d, want 200", status)
	}
	if got := f.store.Devices["laptop"].Name; got != exact {
		t.Errorf("stored name is not bounded: %d characters", len(got))
	}
	// The limit counts characters. Cutting bytes would split a character in two.
	f.rename(t, strings.Repeat("名", maxName+1), "owner-session")
	if got := f.store.Devices["laptop"].Name; got != strings.Repeat("名", maxName) {
		t.Errorf("multi-byte name was cut incorrectly: %q", got)
	}
}

func TestEachChangeIsAuditedOnce(t *testing.T) {
	f := newFixture(t)
	f.rename(t, "Desk", "owner-session")
	f.rename(t, "Office", "owner-session")
	if want := []string{"device.renamed", "device.renamed"}; !reflect.DeepEqual(f.store.Audits, want) {
		t.Errorf("audit records: got %v, want %v", f.store.Audits, want)
	}
}

func TestCredentialNeverLeavesTheServer(t *testing.T) {
	f := newFixture(t)
	status, body := f.rename(t, "Desk", "owner-session")
	if status != http.StatusOK || strings.Contains(body, secret) {
		t.Errorf("credential leaked or call failed: %d %s", status, body)
	}
}

func TestUnpaidEventGrantsNothing(t *testing.T) {
	f := newFixture(t)
	if status, _ := f.deliver(t, "evt_open"); status != http.StatusConflict {
		t.Errorf("got %d, want 409", status)
	}
	if got := f.store.Credits["owner"]; got != 0 {
		t.Errorf("unpaid event granted %d credits", got)
	}
}

func TestProviderOutageGrantsNothing(t *testing.T) {
	f := newFixture(t)
	f.providerDown = true
	if status, _ := f.deliver(t, "evt_paid"); status != http.StatusBadGateway {
		t.Errorf("got %d, want 502", status)
	}
	if got := f.store.Credits["owner"]; got != 0 {
		t.Errorf("outage granted %d credits", got)
	}
}

func TestReplayAndConcurrentDeliveryGrantOnce(t *testing.T) {
	f := newFixture(t)
	var group sync.WaitGroup
	statuses := make([]int, 6)
	for index := range statuses {
		group.Add(1)
		go func() {
			defer group.Done()
			statuses[index], _ = f.deliver(t, "evt_paid")
		}()
	}
	group.Wait()
	for _, status := range statuses {
		if status != http.StatusOK {
			t.Errorf("delivery failed with %d", status)
		}
	}
	if got := f.store.Credits["owner"]; got != 500 {
		t.Errorf("concurrent deliveries granted %d credits, want 500 once", got)
	}
	f.deliver(t, "evt_paid")
	if got := f.store.Credits["owner"]; got != 500 {
		t.Errorf("a later replay granted credits: %d", got)
	}
}
