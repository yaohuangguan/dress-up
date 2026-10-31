// Package deviceapi is a small API with ownership, input limits, an audit trail, a
// secret field and a replayable payment webhook.
package deviceapi

import (
	"encoding/json"
	"net/http"
	"net/url"
	"strings"
	"sync"
)

const maxName = 80

// Device holds a credential that must never be returned to a caller.
type Device struct {
	ID         string
	Owner      string
	Name       string
	Credential string
}

// Store keeps state in memory. A real service would use its database here.
type Store struct {
	mu       sync.Mutex
	Sessions map[string]string
	Devices  map[string]*Device
	Audits   []string
	Paid     map[string]bool
	Credits  map[string]int
}

type providerEvent struct {
	Status  string `json:"status"`
	UserID  string `json:"user_id"`
	Credits int    `json:"credits"`
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("content-type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}

// NewHandler returns the API. The provider URL and client are the network boundary.
func NewHandler(store *Store, providerURL string, client *http.Client) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /devices/{id}/rename", func(w http.ResponseWriter, r *http.Request) {
		rename(store, w, r)
	})
	mux.HandleFunc("POST /webhooks/payment", func(w http.ResponseWriter, r *http.Request) {
		paymentWebhook(store, providerURL, client, w, r)
	})
	return mux
}

func rename(store *Store, w http.ResponseWriter, r *http.Request) {
	store.mu.Lock()
	defer store.mu.Unlock()
	var userID string
	if cookie, err := r.Cookie("session"); err == nil {
		userID = store.Sessions[cookie.Value]
	}
	if userID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	device := store.Devices[r.PathValue("id")]
	if device == nil || device.Owner != userID {
		writeError(w, http.StatusNotFound, "device not found")
		return
	}
	var body struct {
		Name string `json:"name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Name) == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	next := strings.TrimSpace(body.Name)
	if runes := []rune(next); len(runes) > maxName {
		next = string(runes[:maxName])
	}
	device.Name = next
	store.Audits = append(store.Audits, "device.renamed")
	writeJSON(w, http.StatusOK, map[string]string{"id": device.ID, "name": next})
}

// Webhooks can arrive twice, so the provider is asked what happened and the stored
// event id decides whether the credit was already granted.
func paymentWebhook(store *Store, providerURL string, client *http.Client, w http.ResponseWriter, r *http.Request) {
	var body struct {
		ID string `json:"id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.ID == "" {
		writeError(w, http.StatusBadRequest, "id is required")
		return
	}
	response, err := client.Get(providerURL + "/v1/events/" + url.PathEscape(body.ID))
	if err != nil {
		writeError(w, http.StatusBadGateway, "payment not verified")
		return
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		writeError(w, http.StatusBadGateway, "payment not verified")
		return
	}
	var event providerEvent
	if err := json.NewDecoder(response.Body).Decode(&event); err != nil {
		writeError(w, http.StatusBadGateway, "payment not verified")
		return
	}
	if event.Status != "paid" {
		writeError(w, http.StatusConflict, "payment not verified")
		return
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	if !store.Paid[body.ID] {
		store.Paid[body.ID] = true
		store.Credits[event.UserID] += event.Credits
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}
