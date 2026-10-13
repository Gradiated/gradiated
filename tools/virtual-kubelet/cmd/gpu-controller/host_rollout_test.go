package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes/fake"
	ktesting "k8s.io/client-go/testing"
)

type rolloutFixture struct {
	mu                 sync.Mutex
	now                time.Time
	rollout            *hostRollout
	client             *fake.Clientset
	versions           map[string]hostVersion
	updates            map[string]int
	identities         map[string]int
	unavailable        map[string]bool
	ready              map[string]bool
	rejectConfigure    bool
	permanentConfigure bool
}

func newRolloutFixture(t *testing.T) *rolloutFixture {
	t.Helper()
	f := &rolloutFixture{now: time.Unix(1000, 0), versions: map[string]hostVersion{}, updates: map[string]int{}, identities: map[string]int{}, unavailable: map[string]bool{}, ready: map[string]bool{}}
	hosts := []host{{InstanceID: "first"}, {InstanceID: "second"}}
	f.client = fake.NewSimpleClientset(&v1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-first"}}, &v1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-second"}})
	f.rollout = newHostRollout(&hostBundle{SHA256: strings.Repeat("a", 64), BaseID: "base"}, hosts)
	f.rollout.now = func() time.Time { return f.now }
	for _, h := range hosts {
		f.versions[h.InstanceID] = hostVersion{InstanceID: h.InstanceID, Launcher: true}
		f.identities[h.InstanceID] = 10
		f.ready[h.InstanceID] = true
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		f.mu.Lock()
		defer f.mu.Unlock()
		id := strings.Trim(req.URL.Path, "/")
		var body map[string]any
		json.NewDecoder(req.Body).Decode(&body)
		switch body["operation"] {
		case "ping":
			if f.unavailable[id] {
				w.WriteHeader(503)
				return
			}
			json.NewEncoder(w).Encode(f.versions[id])
		case "list":
			json.NewEncoder(w).Encode([]*v1.Pod{{ObjectMeta: metav1.ObjectMeta{UID: types.UID(id + "-pod")}}})
		case "status":
			json.NewEncoder(w).Encode(map[string]any{"running": true, "ready": f.ready[id], "epoch": map[string]any{"pid": f.identities[id], "birth": "100"}})
		case "configure":
			if body["host_bundle"] != nil {
				f.updates[id]++
				if f.permanentConfigure {
					w.WriteHeader(422)
					return
				}
				if f.rejectConfigure {
					w.WriteHeader(503)
					return
				}
			}
			w.Write([]byte("{}"))
		default:
			t.Errorf("unexpected operation %v", body["operation"])
			w.WriteHeader(422)
		}
	}))
	t.Cleanup(server.Close)
	token := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(token, []byte("test"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, h := range hosts {
		h.Endpoint = server.URL + "/" + h.InstanceID
		h.TokenFile = token
		f.rollout.register(&provider{host: h, client: f.client.CoreV1(), epoch: 1, term: "term"})
	}
	return f
}

func (f *rolloutFixture) updatesFor(id string) int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.updates[id]
}

func (f *rolloutFixture) step(delay time.Duration) {
	f.now = f.now.Add(delay)
	f.rollout.step(context.Background())
}

func (f *rolloutFixture) apply(id string) {
	f.mu.Lock()
	version := f.versions[id]
	version.Current = f.rollout.pin.SHA256
	f.versions[id] = version
	f.mu.Unlock()
}

func (f *rolloutFixture) state(t *testing.T, id string) hostCheckpoint {
	t.Helper()
	node, err := f.client.CoreV1().Nodes().Get(context.Background(), "gpu-"+id, metav1.GetOptions{})
	if err != nil {
		t.Fatal(err)
	}
	value, err := checkpoint(node, f.rollout.pin.SHA256)
	if err != nil {
		t.Fatal(err)
	}
	return value
}

func TestHostRolloutSerialSoakAndLeaderResume(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	if f.updatesFor("first") != 1 || f.updatesFor("second") != 0 {
		t.Fatal("rollout was not serialized")
	}
	saved := f.state(t, "first")
	if saved.Phase != "updating" || saved.Baseline["first-pod"] != "10:100" {
		t.Fatal("baseline not durable before update")
	}
	f.apply("first")
	f.step(10 * time.Second)
	for i := 0; i < 24; i++ {
		f.step(10 * time.Second)
	}
	if f.rollout.active != "first" {
		t.Fatal("soak ended before five minutes")
	}
	fresh := newHostRollout(f.rollout.pin, []host{{InstanceID: "first"}, {InstanceID: "second"}})
	fresh.now = f.rollout.now
	for _, p := range f.rollout.snapshot() {
		fresh.register(p)
	}
	f.rollout = fresh
	f.step(10 * time.Second)
	if fresh.active != "first" {
		t.Fatal("leader did not resume in-progress host")
	}
	for i := 0; i < 30; i++ {
		f.step(10 * time.Second)
	}
	if f.state(t, "first").Phase != "ready" {
		t.Fatal("completed soak was not persisted")
	}
	f.step(10 * time.Second)
	if f.updatesFor("second") != 1 {
		t.Fatal("second host did not advance after soak")
	}
}

func TestHostRolloutFailurePersistenceRetriesAndSurvivesLeadership(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	f.mu.Lock()
	f.identities["first"] = 20
	f.mu.Unlock()
	var attempts atomic.Int32
	f.client.PrependReactor("patch", "nodes", func(ktesting.Action) (bool, runtime.Object, error) {
		if attempts.Add(1) == 1 {
			return true, nil, fmt.Errorf("API unavailable")
		}
		return false, nil, nil
	})
	f.step(10 * time.Second)
	if f.rollout.failure == nil || f.rollout.failure.persisted {
		t.Fatal("failed persistence was not retained for retry")
	}
	f.step(10 * time.Second)
	if !f.rollout.failure.persisted || f.state(t, "first").Phase != "failed" {
		t.Fatal("failure was not retried")
	}
	fresh := newHostRollout(f.rollout.pin, []host{{InstanceID: "first"}, {InstanceID: "second"}})
	fresh.now = f.rollout.now
	for _, p := range f.rollout.snapshot() {
		fresh.register(p)
	}
	fresh.step(context.Background())
	if fresh.failure == nil {
		t.Fatal("new leader forgot the failure")
	}
	if f.updatesFor("second") != 0 {
		t.Fatal("failure advanced another host")
	}
}

func TestMetricsAndPingRemainResponsiveDuringBlockedRolloutIO(t *testing.T) {
	f := newRolloutFixture(t)
	entered, release := make(chan struct{}), make(chan struct{})
	var first atomic.Bool
	f.client.PrependReactor("get", "nodes", func(ktesting.Action) (bool, runtime.Object, error) {
		if first.CompareAndSwap(false, true) {
			close(entered)
			<-release
		}
		return false, nil, nil
	})
	done := make(chan struct{})
	go func() { f.rollout.step(context.Background()); close(done) }()
	<-entered
	defer func() { close(release); <-done }()
	responsive := make(chan error, 1)
	p := f.rollout.snapshot()["second"]
	go func() { f.rollout.metrics(httptest.NewRecorder(), nil); responsive <- p.Ping(context.Background()) }()
	select {
	case err := <-responsive:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("rollout IO blocked metrics or Ping")
	}
}

func TestRestartDetectsUnreachableInProgressHost(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	fresh := newHostRollout(f.rollout.pin, []host{{InstanceID: "first"}, {InstanceID: "second"}})
	fresh.now = f.rollout.now
	for _, p := range f.rollout.snapshot() {
		fresh.register(p)
	}
	f.rollout = fresh
	f.mu.Lock()
	f.unavailable["first"] = true
	f.mu.Unlock()
	f.step(10 * time.Second)
	if fresh.active != "first" {
		t.Fatal("in-progress checkpoint was lost when host was unreachable")
	}
	f.step(120 * time.Second)
	if fresh.failure == nil || f.state(t, "first").Phase != "failed" {
		t.Fatal("unreachable update did not stop")
	}
}

func TestHostRolloutHealthGraceStartsAtApplication(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	f.apply("first")
	f.mu.Lock()
	f.ready["first"] = false
	f.mu.Unlock()
	f.step(20 * time.Minute)
	if f.rollout.failure != nil {
		t.Fatal("download time consumed the agent health grace")
	}
	f.step(119 * time.Second)
	if f.rollout.failure != nil {
		t.Fatal("health grace ended too soon")
	}
	f.step(time.Second)
	if f.rollout.failure == nil {
		t.Fatal("unhealthy updated host did not stop")
	}
}

func TestHostRolloutRetriesAmbiguousConfigureResponse(t *testing.T) {
	f := newRolloutFixture(t)
	f.mu.Lock()
	f.rejectConfigure = true
	f.mu.Unlock()
	f.step(0)
	if f.rollout.failure != nil {
		t.Fatal("transient configure response permanently rejected a release")
	}
	f.mu.Lock()
	f.rejectConfigure = false
	f.mu.Unlock()
	f.step(10 * time.Second)
	if f.updatesFor("first") != 2 || f.updatesFor("second") != 0 {
		t.Fatal("configure was not retried on the same host")
	}
}

func TestHostRolloutPauseResetsSoak(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	f.apply("first")
	f.step(10 * time.Second)
	for i := 0; i < 24; i++ {
		f.step(10 * time.Second)
	}
	f.step(time.Minute)
	for i := 0; i < 6; i++ {
		f.step(10 * time.Second)
	}
	if f.state(t, "first").Phase == "ready" {
		t.Fatal("missing observations counted toward continuous soak")
	}
}

func TestHostPinValidationAndDisabledLegacyRollout(t *testing.T) {
	for _, pin := range []*hostBundle{{SHA256: "bad", BaseID: "base"}, {SHA256: strings.Repeat("a", 64), BaseID: "../base"}} {
		if pin.validate() == nil {
			t.Fatal("invalid pin accepted")
		}
	}
	f := newRolloutFixture(t)
	f.rollout.pin = nil
	f.mu.Lock()
	f.versions["first"] = hostVersion{InstanceID: "first"}
	f.mu.Unlock()
	f.step(0)
	if f.rollout.failure != nil || len(f.updates) != 0 {
		t.Fatal("disabled rollout rejected a legacy agent")
	}
	recorder := httptest.NewRecorder()
	f.rollout.metrics(recorder, nil)
	if !strings.Contains(recorder.Body.String(), "gradiated_gpu_host_bundle_info") {
		t.Fatal("version metric missing")
	}
}

func TestServingRequiresEveryAssignedModelPod(t *testing.T) {
	f := newRolloutFixture(t)
	_, err := f.client.CoreV1().Pods("gpu-inference").Create(context.Background(), &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "model", Namespace: "gpu-inference", UID: types.UID("missing")}, Spec: v1.PodSpec{NodeName: "gpu-first"}}, metav1.CreateOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := f.rollout.snapshot()["first"].serving(context.Background()); err == nil {
		t.Fatal("host passed while dropping an assigned model")
	}
}

func TestControlPlaneOutagePausesWithoutRejectingHealthyAgent(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	var unavailable atomic.Bool
	unavailable.Store(true)
	f.client.PrependReactor("get", "nodes", func(ktesting.Action) (bool, runtime.Object, error) {
		if unavailable.Load() {
			return true, nil, fmt.Errorf("API unavailable")
		}
		return false, nil, nil
	})
	f.step(10 * time.Second)
	f.step(120 * time.Second)
	if f.rollout.failure != nil {
		t.Fatal("control-plane outage was mistaken for host failure")
	}
	unavailable.Store(false)
	f.step(10 * time.Second)
	if f.updatesFor("first") != 2 || f.updatesFor("second") != 0 {
		t.Fatal("rollout did not resume on its active host")
	}
}

func TestPermanentConfigureRejectionStopsImmediately(t *testing.T) {
	f := newRolloutFixture(t)
	f.mu.Lock()
	f.permanentConfigure = true
	f.mu.Unlock()
	f.step(0)
	if f.rollout.failure == nil || f.state(t, "first").Phase != "failed" {
		t.Fatal("permanent host rejection was retried")
	}
	f.step(10 * time.Second)
	if f.updatesFor("first") != 1 || f.updatesFor("second") != 0 {
		t.Fatal("rejected host release advanced")
	}
}

func TestSlowHealthyStagingStillReceivesFullSoak(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	f.apply("first")
	f.mu.Lock()
	version := f.versions["first"]
	version.Trial = true
	f.versions["first"] = version
	f.mu.Unlock()
	f.step(30 * time.Minute)
	f.mu.Lock()
	version.Trial = false
	f.versions["first"] = version
	f.mu.Unlock()
	f.step(100 * time.Second)
	for i := 0; i < 30; i++ {
		f.step(10 * time.Second)
	}
	if f.rollout.failure != nil || f.state(t, "first").Phase != "ready" {
		t.Fatal("slow healthy staging consumed the soak budget")
	}
}

func TestTransientServingFailureRestartsSoakWithoutRejectingRelease(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	f.apply("first")
	f.step(10 * time.Second)
	for i := 0; i < 24; i++ {
		f.step(10 * time.Second)
	}
	f.mu.Lock()
	f.ready["first"] = false
	f.mu.Unlock()
	f.step(10 * time.Second)
	if f.rollout.failure != nil {
		t.Fatal("transient readiness loss rejected a healthy release")
	}
	f.mu.Lock()
	f.ready["first"] = true
	f.mu.Unlock()
	f.step(10 * time.Second)
	if f.state(t, "first").Phase == "ready" {
		t.Fatal("readiness loss did not restart the soak")
	}
	for i := 0; i < 30; i++ {
		f.step(10 * time.Second)
	}
	if f.state(t, "first").Phase != "ready" {
		t.Fatal("rollout did not recover after transient readiness loss")
	}
}

func TestReachabilityRecoveryResetsGraceWhileAnotherHostIsUnavailable(t *testing.T) {
	f := newRolloutFixture(t)
	f.step(0)
	f.unavailable["first"] = true
	f.step(10 * time.Second)
	f.unavailable["first"], f.unavailable["second"] = false, true
	f.step(time.Minute)
	f.unavailable["first"] = true
	f.step(time.Minute)
	if f.rollout.failure != nil {
		t.Fatal("separate outages consumed a continuous failure grace")
	}
	f.step(120 * time.Second)
	if f.rollout.failure == nil {
		t.Fatal("continuous active-host outage did not stop the update")
	}
}
