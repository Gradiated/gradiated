package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	corelisters "k8s.io/client-go/listers/core/v1"
	"k8s.io/client-go/tools/cache"
)

func testProvider(t *testing.T, handler http.HandlerFunc) *provider {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)
	token := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(token, []byte("host-only-key"), 0600); err != nil {
		t.Fatal(err)
	}
	return &provider{host: host{Endpoint: server.URL, TokenFile: token}, epoch: 7, pods: map[string]*v1.Pod{}}
}

func TestOriginalPodPreventsResolvedCredentialTransfer(t *testing.T) {
	calls := 0
	p := testProvider(t, func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.Header.Get("Authorization") != "Bearer host-only-key" {
			t.Error("missing management credential")
		}
		var body struct {
			Epoch int
			Pod   v1.Pod
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body.Epoch != 7 || len(body.Pod.Spec.Containers[0].Env) != 0 {
			t.Error("incorrect original spec or fencing epoch")
		}
		_, _ = w.Write([]byte(`{"created":true}`))
	})
	store := cache.NewIndexer(cache.MetaNamespaceKeyFunc, cache.Indexers{cache.NamespaceIndex: cache.MetaNamespaceIndexFunc})
	original := &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "kev", Namespace: "gpu-inference", UID: types.UID("uid")}, Spec: v1.PodSpec{Containers: []v1.Container{{Name: "runtime", Image: "kev"}}}}
	if err := store.Add(original); err != nil {
		t.Fatal(err)
	}
	p.source = corelisters.NewPodLister(store)
	resolved := original.DeepCopy()
	resolved.Spec.Containers[0].Env = []v1.EnvVar{{Name: "DATABASE_URL", Value: "must-not-reach-host"}}
	if err := p.CreatePod(context.Background(), resolved); err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Fatal("host create was not called")
	}
	original.Spec.Containers[0].EnvFrom = []v1.EnvFromSource{{SecretRef: &v1.SecretEnvSource{LocalObjectReference: v1.LocalObjectReference{Name: "db"}}}}
	if err := store.Update(original); err != nil {
		t.Fatal(err)
	}
	if err := p.CreatePod(context.Background(), original); err == nil {
		t.Fatal("secret-backed runtime accepted")
	}
	if calls != 1 {
		t.Fatal("unsafe pod was sent to host")
	}
}

func TestManagementCredentialDoesNotFollowRedirect(t *testing.T) {
	reached := false
	destination := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { reached = true }))
	defer destination.Close()
	p := testProvider(t, func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, destination.URL, http.StatusTemporaryRedirect)
	})
	var result any
	if err := p.call(context.Background(), "ping", "", nil, &result); err == nil {
		t.Fatal("redirect accepted")
	}
	if reached {
		t.Fatal("management credential sent to redirect target")
	}
}
