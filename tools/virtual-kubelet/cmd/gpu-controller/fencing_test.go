package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/virtual-kubelet/virtual-kubelet/errdefs"
	coordination "k8s.io/api/coordination/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/uuid"
	"k8s.io/client-go/kubernetes/fake"
)

// realHost starts the shipped host agent with its fence file under root.
func realHost(t *testing.T, ctx context.Context) (host, string) {
	t.Helper()
	root := t.TempDir()
	command := exec.CommandContext(ctx, "python3", "../../fencing_fixture.py", root)
	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err = command.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { command.Process.Kill(); command.Wait() })
	endpoint, err := bufio.NewReader(stdout).ReadString('\n')
	if err != nil {
		t.Fatal(err)
	}
	token := filepath.Join(root, "token")
	if err = os.WriteFile(token, []byte("host-only-key"), 0600); err != nil {
		t.Fatal(err)
	}
	return host{Endpoint: strings.TrimSpace(endpoint), TokenFile: token}, root
}

func TestRealHostFencingSurvivesLeaseReplacementAndRejectsStaleController(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	h, root := realHost(t, ctx)
	holder := "leader-1"
	acquired := metav1.NewMicroTime(time.Now())
	lease := &coordination.Lease{ObjectMeta: metav1.ObjectMeta{Name: "gpu-controller", Namespace: "gpu-inference", UID: types.UID("lease-1")}, Spec: coordination.LeaseSpec{HolderIdentity: &holder, AcquireTime: &acquired}}
	client := fake.NewSimpleClientset(lease)
	term := string(uuid.NewUUID())
	epoch, err := claimHost(ctx, client, "gpu-inference", holder, lease, term, h)
	if err != nil || epoch != 1 {
		t.Fatalf("initial claim: %d %v", epoch, err)
	}
	retry, err := claimHost(ctx, client, "gpu-inference", holder, lease, term, h)
	if err != nil || retry != epoch {
		t.Fatalf("retry changed generation: %d %v", retry, err)
	}
	old := lease.DeepCopy()
	if err = client.CoordinationV1().Leases(lease.Namespace).Delete(ctx, lease.Name, metav1.DeleteOptions{}); err != nil {
		t.Fatal(err)
	}
	lease.UID = types.UID("lease-2")
	holder = "leader-2"
	lease.Spec.HolderIdentity = &holder
	if _, err = client.CoordinationV1().Leases(lease.Namespace).Create(ctx, lease, metav1.CreateOptions{}); err != nil {
		t.Fatal(err)
	}
	if _, err = claimHost(ctx, client, lease.Namespace, "leader-1", old, string(uuid.NewUUID()), h); err == nil {
		t.Fatal("stale leader claimed host")
	}
	newTerm := string(uuid.NewUUID())
	newer, err := claimHost(ctx, client, lease.Namespace, holder, lease, newTerm, h)
	if err != nil || newer != 2 {
		t.Fatalf("recreated lease could not fence old leader: %d %v", newer, err)
	}
	var result any
	stale := &provider{host: h, fence: &hostFence{epoch: epoch, term: term}}
	if err = stale.call(ctx, "list", "", nil, &result); err == nil {
		t.Fatal("stale host operation accepted")
	}
	stale.fence.epoch = newer
	if err = stale.call(ctx, "list", "", nil, &result); err == nil {
		t.Fatal("old term matched the new generation")
	}
	current := &provider{host: h, fence: &hostFence{epoch: newer, term: newTerm}}
	if err = current.call(ctx, "list", "", nil, &result); err != nil {
		t.Fatal(err)
	}
	contents, err := os.ReadFile(filepath.Join(root, "fence.json"))
	if err != nil {
		t.Fatal(err)
	}
	var durable struct{ Epoch int64 }
	if err = json.Unmarshal(contents, &durable); err != nil || durable.Epoch != newer {
		t.Fatal("generation was not persisted")
	}
}

func testLease(holder, uid string) *coordination.Lease {
	acquired := metav1.NewMicroTime(time.Now())
	return &coordination.Lease{ObjectMeta: metav1.ObjectMeta{Name: "gpu-controller", Namespace: "gpu-inference", UID: types.UID(uid)}, Spec: coordination.LeaseSpec{HolderIdentity: &holder, AcquireTime: &acquired}}
}

func hostEpoch(t *testing.T, ctx context.Context, h host) int64 {
	t.Helper()
	var current struct{ Epoch int64 }
	if err := (&provider{host: h}).callPayload(ctx, map[string]any{"operation": "fence"}, &current); err != nil {
		t.Fatal(err)
	}
	return current.Epoch
}

func TestLeaderReclaimsAHostWhoseFenceWasReset(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	h, root := realHost(t, ctx)
	lease := testLease("leader-1", "lease-1")
	client := fake.NewSimpleClientset(lease)
	if _, err := claimHost(ctx, client, "gpu-inference", "leader-1", lease, string(uuid.NewUUID()), h); err != nil {
		t.Fatal(err)
	}
	term := string(uuid.NewUUID())
	epoch, err := claimHost(ctx, client, "gpu-inference", "leader-1", lease, term, h)
	if err != nil || epoch != 2 {
		t.Fatalf("claim: %d %v", epoch, err)
	}
	lost := false
	p := &provider{host: h, fence: leaderFence(client, "gpu-inference", "leader-1", lease, term, h, epoch, func() { lost = true })}
	var pods []any
	if err = p.call(ctx, "list", "", nil, &pods); err != nil {
		t.Fatal(err)
	}
	// A re-image starts the host with no fence file.
	if err = os.Remove(filepath.Join(root, "fence.json")); err != nil {
		t.Fatal(err)
	}
	if err = p.call(ctx, "list", "", nil, &pods); err != nil {
		t.Fatalf("operation after reset: %v", err)
	}
	if held, _ := p.fence.current(); held != 1 || hostEpoch(t, ctx, h) != 1 || lost {
		t.Fatalf("re-claim held %d, host %d", held, hostEpoch(t, ctx, h))
	}
	// The pod controller shares the fence and uses the new generation directly.
	shared := &provider{host: h, fence: p.fence}
	if err = shared.call(ctx, "list", "", nil, &pods); err != nil {
		t.Fatal(err)
	}
}

func TestControllerDoesNotOverrideAHostAnotherLeaderClaimed(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	h, _ := realHost(t, ctx)
	lease := testLease("leader-1", "lease-1")
	client := fake.NewSimpleClientset(lease)
	term := string(uuid.NewUUID())
	epoch, err := claimHost(ctx, client, "gpu-inference", "leader-1", lease, term, h)
	if err != nil || epoch != 1 {
		t.Fatalf("claim: %d %v", epoch, err)
	}
	p := &provider{host: h, fence: leaderFence(client, "gpu-inference", "leader-1", lease, term, h, epoch, func() {})}
	// Another term claims the host even though the lease check still passes:
	// the host moved forward, so this controller must not take it back.
	if _, err = claimHost(ctx, client, "gpu-inference", "leader-1", lease, string(uuid.NewUUID()), h); err != nil {
		t.Fatal(err)
	}
	var pods []any
	err = p.call(ctx, "list", "", nil, &pods)
	var stale *staleFenceError
	if !errors.As(err, &stale) || !errdefs.IsInvalidInput(err) || !errors.Is(stale.refused, errHostAhead) {
		t.Fatalf("controller behind the host: %v", err)
	}
	if held, _ := p.fence.current(); held != 1 || hostEpoch(t, ctx, h) != 2 {
		t.Fatalf("controller moved the fence: held %d, host %d", held, hostEpoch(t, ctx, h))
	}
}

func TestFormerLeaderDoesNotReclaimAResetHost(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	h, root := realHost(t, ctx)
	lease := testLease("leader-1", "lease-1")
	client := fake.NewSimpleClientset(lease)
	term := string(uuid.NewUUID())
	epoch, err := claimHost(ctx, client, "gpu-inference", "leader-1", lease, term, h)
	if err != nil {
		t.Fatal(err)
	}
	lost := false
	former := &provider{host: h, fence: leaderFence(client, "gpu-inference", "leader-1", lease, term, h, epoch, func() { lost = true })}
	if err = client.CoordinationV1().Leases("gpu-inference").Delete(ctx, "gpu-controller", metav1.DeleteOptions{}); err != nil {
		t.Fatal(err)
	}
	if _, err = client.CoordinationV1().Leases("gpu-inference").Create(ctx, testLease("leader-2", "lease-2"), metav1.CreateOptions{}); err != nil {
		t.Fatal(err)
	}
	if err = os.Remove(filepath.Join(root, "fence.json")); err != nil {
		t.Fatal(err)
	}
	var pods []any
	err = former.call(ctx, "list", "", nil, &pods)
	var stale *staleFenceError
	if !errors.As(err, &stale) || !errors.Is(stale.refused, errLeadershipChanged) {
		t.Fatalf("former leader: %v", err)
	}
	if !lost || hostEpoch(t, ctx, h) != 0 {
		t.Fatalf("former leader claimed the reset host: lost=%v host=%d", lost, hostEpoch(t, ctx, h))
	}
}

func TestConfigureRetriesOnceWithTheReclaimedGeneration(t *testing.T) {
	var epochs []float64
	p := testProvider(t, func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		epochs = append(epochs, body["epoch"].(float64))
		if body["epoch"] != float64(1) {
			w.WriteHeader(http.StatusConflict)
			_, _ = w.Write([]byte(`{"error":"stale_epoch"}`))
			return
		}
		_, _ = w.Write([]byte(`{}`))
	})
	p.host.InstanceID = first
	p.host.Runtimes = json.RawMessage(`{"kev":{}}`)
	claims := 0
	p.fence.claim = func(_ context.Context, held int64) (int64, error) {
		claims++
		if held != 7 {
			t.Errorf("re-claim below %d", held)
		}
		return 1, nil
	}
	if err := configureHost(context.Background(), fleetClient(gpuHostObject(first, 4)), p); err != nil {
		t.Fatal(err)
	}
	if claims != 1 || len(epochs) != 2 || epochs[0] != 7 || epochs[1] != 1 {
		t.Fatalf("claims %d, epochs %v", claims, epochs)
	}
	// A host that still rejects the re-claimed generation fails the operation.
	p.fence.epoch = 3
	epochs = nil
	p.fence.claim = func(context.Context, int64) (int64, error) { claims++; return 4, nil }
	err := configureHost(context.Background(), fleetClient(gpuHostObject(first, 4)), p)
	var stale *staleFenceError
	if !errors.As(err, &stale) || !errdefs.IsInvalidInput(err) || claims != 2 || len(epochs) != 2 {
		t.Fatalf("err %v, claims %d, epochs %v", err, claims, epochs)
	}
	// An unreachable host during the re-claim stays a retryable failure.
	p.fence.epoch = 3
	p.fence.claim = func(context.Context, int64) (int64, error) {
		return 0, errors.New("host temporarily unavailable: synthetic")
	}
	err = configureHost(context.Background(), fleetClient(gpuHostObject(first, 4)), p)
	if err == nil || errdefs.IsInvalidInput(err) {
		t.Fatalf("transient re-claim failure: %v", err)
	}
}
