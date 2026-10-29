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
	"k8s.io/client-go/kubernetes/fake"
	corelisters "k8s.io/client-go/listers/core/v1"
	ktesting "k8s.io/client-go/testing"
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
	return &provider{host: host{Endpoint: server.URL, TokenFile: token}, fence: &hostFence{epoch: 7}, pods: map[string]*v1.Pod{}}
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

func TestStatusUpdatePreservesQualificationAndRejectsReusedPodName(t *testing.T) {
	original := &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "kev", Namespace: "gpu-inference", UID: types.UID("current-uid"), Annotations: map[string]string{"gradiated.com/qualified": "true"}}}
	client := fake.NewSimpleClientset(original)
	pods := statusClient{client.CoreV1()}.Pods("gpu-inference")
	stale := original.DeepCopy()
	stale.Annotations = nil
	stale.Status.Phase = v1.PodRunning
	result, err := pods.UpdateStatus(context.Background(), stale, metav1.UpdateOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if result.Annotations["gradiated.com/qualified"] != "true" || result.Status.Phase != v1.PodRunning {
		t.Fatal("status update changed qualification")
	}
	stale.UID = types.UID("previous-uid")
	stale.Status.Phase = v1.PodFailed
	if _, err = pods.UpdateStatus(context.Background(), stale, metav1.UpdateOptions{}); err == nil {
		t.Fatal("status update crossed Pod UID boundary")
	}
}

func TestDeletionReleasesKubernetesPodOnlyAfterHostCleanup(t *testing.T) {
	p := testProvider(t, func(w http.ResponseWriter, r *http.Request) { w.Write([]byte(`{"deleted":true}`)) })
	pod := &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "drained", Namespace: "gpu-inference", UID: types.UID("old-uid")}}
	client := fake.NewSimpleClientset(pod)
	p.client = client.CoreV1()
	if err := p.DeletePod(context.Background(), pod); err != nil {
		t.Fatal(err)
	}
	actions := client.Actions()
	if len(actions) != 1 || actions[0].GetVerb() != "delete" {
		t.Fatalf("expected one deletion, got %v", actions)
	}
	options := actions[0].(ktesting.DeleteAction).GetDeleteOptions()
	if options.GracePeriodSeconds == nil || *options.GracePeriodSeconds != 0 || options.Preconditions == nil || *options.Preconditions.UID != pod.UID {
		t.Fatalf("unsafe deletion options: %+v", options)
	}
}

func TestTransientProviderFailureKeepsTrainingJobPending(t *testing.T) {
	original := &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "training", Namespace: "gpu-inference", UID: types.UID("training-uid")}}
	client := fake.NewSimpleClientset(original)
	failed := original.DeepCopy()
	failed.Status = v1.PodStatus{Phase: v1.PodFailed, Reason: "ProviderFailed", Message: "host temporarily unavailable: operation create returned 503"}
	result, err := (statusClient{client.CoreV1()}).Pods("gpu-inference").UpdateStatus(context.Background(), failed, metav1.UpdateOptions{})
	if err != nil || result.Status.Phase != v1.PodPending {
		t.Fatalf("transient staging failure completed Job: %v", err)
	}
	failed.Status.Message = "host operation create returned 422"
	result, err = (statusClient{client.CoreV1()}).Pods("gpu-inference").UpdateStatus(context.Background(), failed, metav1.UpdateOptions{})
	if err != nil || result.Status.Phase != v1.PodFailed {
		t.Fatalf("invalid runtime was not rejected: %v", err)
	}
}

func TestCreationStartsCatalogueStagingBeforeRequestingRuntime(t *testing.T) {
	var operations []string
	p := testProvider(t, func(w http.ResponseWriter, r *http.Request) {
		var b struct{ Operation string }
		if err := json.NewDecoder(r.Body).Decode(&b); err != nil {
			t.Fatal(err)
		}
		operations = append(operations, b.Operation)
		w.Write([]byte(`{}`))
	})
	p.host.Runtimes = json.RawMessage(`{"pinned":{}}`)
	store := cache.NewIndexer(cache.MetaNamespaceKeyFunc, cache.Indexers{cache.NamespaceIndex: cache.MetaNamespaceIndexFunc})
	pod := &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "training", Namespace: "gpu-inference", UID: types.UID("uid")}, Spec: v1.PodSpec{Containers: []v1.Container{{Name: "runtime", Image: "training"}}}}
	if err := store.Add(pod); err != nil {
		t.Fatal(err)
	}
	p.source = corelisters.NewPodLister(store)
	if err := p.CreatePod(context.Background(), pod); err != nil {
		t.Fatal(err)
	}
	if len(operations) != 2 || operations[0] != "configure" || operations[1] != "create" {
		t.Fatalf("creation raced catalogue staging: %v", operations)
	}
}

func TestExitedServingTaskWaitsForRecoveryButTrainingFails(t *testing.T) {
	p := testProvider(t, func(w http.ResponseWriter, r *http.Request) { w.Write([]byte(`{"running":false,"ready":false}`)) })
	pod := &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "runtime", Namespace: "gpu-inference", UID: types.UID("uid")}, Spec: v1.PodSpec{RestartPolicy: v1.RestartPolicyAlways}}
	p.pods["gpu-inference/runtime"] = pod
	status, err := p.GetPodStatus(context.Background(), pod.Namespace, pod.Name)
	if err != nil || status.Phase != v1.PodPending {
		t.Fatalf("serving process cannot recover: %v %v", status, err)
	}
	pod.Spec.RestartPolicy = v1.RestartPolicyNever
	status, err = p.GetPodStatus(context.Background(), pod.Namespace, pod.Name)
	if err != nil || status.Phase != v1.PodFailed {
		t.Fatalf("training failure would be retried: %v %v", status, err)
	}
}

func TestPodLostByAReachableHostFailsSoItIsReplaced(t *testing.T) {
	body := `{"error":"unknown_pod"}`
	p := testProvider(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(body))
	})
	pod := &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "runtime", Namespace: "gpu-inference", UID: types.UID("uid")}, Spec: v1.PodSpec{RestartPolicy: v1.RestartPolicyAlways}}
	p.pods["gpu-inference/runtime"] = pod
	status, err := p.GetPodStatus(context.Background(), pod.Namespace, pod.Name)
	if err != nil || status.Phase != v1.PodFailed || status.Reason != "RuntimeLost" {
		t.Fatalf("lost runtime is not replaced: %v %v", status, err)
	}
	// Any other 404, such as a misrouted proxy, stays a temporary host failure.
	body = `not found`
	status, err = p.GetPodStatus(context.Background(), pod.Namespace, pod.Name)
	if err != nil || status.Phase != v1.PodRunning || status.Reason != "HostUnreachable" {
		t.Fatalf("an unrelated 404 failed the pod: %v %v", status, err)
	}
}
