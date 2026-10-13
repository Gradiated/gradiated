package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/fake"
)

func TestHostRolloutSerialSoakAndFailure(t *testing.T) {
	now := time.Unix(1000, 0)
	pin := &hostBundle{SHA256: strings.Repeat("a", 64), BaseID: "base"}
	hosts := []host{{InstanceID: "first"}, {InstanceID: "second"}}
	r := newHostRollout(pin, hosts)
	r.now = func() time.Time { return now }
	client := fake.NewSimpleClientset(&v1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-first"}}, &v1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-second"}})
	calls := map[string]int{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body map[string]any
		json.NewDecoder(req.Body).Decode(&body)
		if body["operation"] == "list" {
			w.Write([]byte("[]"))
			return
		}
		if body["operation"] == "configure" {
			if body["host_bundle"] == nil {
				t.Error("host pin missing")
			}
			calls[req.URL.Path]++
		}
		w.Write([]byte("{}"))
	}))
	defer server.Close()
	token := filepath.Join(t.TempDir(), "token")
	os.WriteFile(token, []byte("test"), 0600)
	providers := map[string]*provider{}
	for _, h := range hosts {
		h.Endpoint = server.URL + "/" + h.InstanceID
		h.TokenFile = token
		providers[h.InstanceID] = &provider{host: h, client: client.CoreV1(), epoch: 1, term: "term"}
	}
	observe := func(id, current string) {
		r.observe(context.Background(), providers[id], hostVersion{InstanceID: id, Current: current, Launcher: true})
	}
	observe("first", "")
	if len(calls) != 0 {
		t.Fatal("updated before observing every host")
	}
	observe("second", "")
	observe("first", "")
	if calls["/first"] != 1 || calls["/second"] != 0 {
		t.Fatalf("not serialized: %v", calls)
	}
	observe("first", pin.SHA256)
	for i := 0; i < 24; i++ {
		now = now.Add(10 * time.Second)
		observe("second", "")
		observe("first", pin.SHA256)
	}
	if r.active != "first" {
		t.Fatal("soak ended too soon")
	}
	for i := 0; i < 6; i++ {
		now = now.Add(10 * time.Second)
		observe("first", pin.SHA256)
	}
	observe("second", "")
	if calls["/second"] != 1 {
		t.Fatalf("second host did not advance: %v", calls)
	}
	r.observe(context.Background(), providers["second"], hostVersion{InstanceID: "second", Failed: pin.SHA256, Launcher: true})
	if !r.failed {
		t.Fatal("rollback did not stop rollout")
	}
	node, _ := client.CoreV1().Nodes().Get(context.Background(), "gpu-second", metav1.GetOptions{})
	if node.Annotations["gradiated.com/host-bundle-failed"] != pin.SHA256 {
		t.Fatal("failure not persisted")
	}
	fresh := newHostRollout(pin, hosts)
	fresh.observe(context.Background(), providers["second"], hostVersion{InstanceID: "second", Launcher: true})
	if !fresh.failed {
		t.Fatal("leader change retried a failed digest")
	}
}

func TestServingRejectsUnready(t *testing.T) {
	token := filepath.Join(t.TempDir(), "token")
	os.WriteFile(token, []byte("test"), 0600)
	ready := false
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		var body map[string]any
		json.NewDecoder(req.Body).Decode(&body)
		if body["operation"] == "list" {
			json.NewEncoder(w).Encode([]*v1.Pod{{ObjectMeta: metav1.ObjectMeta{UID: types.UID("pod")}}})
			return
		}
		json.NewEncoder(w).Encode(map[string]any{"running": true, "ready": ready, "epoch": map[string]any{"pid": 10, "birth": "100"}})
	}))
	defer server.Close()
	p := &provider{host: host{Endpoint: server.URL, TokenFile: token}}
	if _, err := p.serving(context.Background()); err == nil {
		t.Fatal("unready model accepted")
	}
	ready = true
	identities, err := p.serving(context.Background())
	if err != nil || identities["pod"] != "10:100" {
		t.Fatalf("identity missing: %v %v", identities, err)
	}
}

func TestHostPinValidationAndLegacyObservation(t *testing.T) {
	for _, pin := range []*hostBundle{{SHA256: "bad", BaseID: "base"}, {SHA256: strings.Repeat("a", 64), BaseID: "../base"}} {
		if pin.validate() == nil {
			t.Fatal("invalid pin accepted")
		}
	}
	r := newHostRollout(nil, []host{{InstanceID: "legacy"}})
	p := &provider{host: host{InstanceID: "legacy"}}
	r.observe(context.Background(), p, hostVersion{InstanceID: "legacy"})
	if r.failed {
		t.Fatal("disabled rollout rejected a legacy agent")
	}
	recorder := httptest.NewRecorder()
	r.metrics(recorder, nil)
	if !strings.Contains(recorder.Body.String(), "gradiated_gpu_host_bundle_info") {
		t.Fatal("version metric missing")
	}
}

func TestServingRequiresEveryAssignedModelPod(t *testing.T) {
	token := filepath.Join(t.TempDir(), "token")
	os.WriteFile(token, []byte("test"), 0600)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("[]")) }))
	defer server.Close()
	client := fake.NewSimpleClientset(&v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "model", Namespace: "gpu-inference", UID: types.UID("missing")}, Spec: v1.PodSpec{NodeName: "gpu-first"}})
	p := &provider{host: host{InstanceID: "first", Endpoint: server.URL, TokenFile: token}, client: client.CoreV1()}
	if _, err := p.serving(context.Background()); err == nil {
		t.Fatal("host passed while dropping an assigned model")
	}
}

func TestUnreachableHostStopsRollout(t *testing.T) {
	now := time.Unix(1000, 0)
	pin := &hostBundle{SHA256: strings.Repeat("a", 64), BaseID: "base"}
	r := newHostRollout(pin, []host{{InstanceID: "first"}})
	r.now = func() time.Time { return now }
	r.active = "first"
	r.hosts["first"] = rolloutHost{seen: now.Add(-121 * time.Second)}
	client := fake.NewSimpleClientset(&v1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-first"}})
	p := &provider{host: host{InstanceID: "first"}, client: client.CoreV1()}
	r.unavailable(context.Background(), p)
	if !r.failed {
		t.Fatal("unreachable host did not stop rollout")
	}
}
