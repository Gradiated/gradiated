package main

import (
	"bufio"
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	coordination "k8s.io/api/coordination/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/uuid"
	"k8s.io/client-go/kubernetes/fake"
)

func TestRealHostFencingSurvivesLeaseReplacementAndRejectsStaleController(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	root := t.TempDir()
	command := exec.CommandContext(ctx, "python3", "../../fencing_fixture.py", root)
	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err = command.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { command.Process.Kill(); command.Wait() }()
	reader := bufio.NewReader(stdout)
	endpoint, err := reader.ReadString('\n')
	if err != nil {
		t.Fatal(err)
	}
	token := filepath.Join(root, "token")
	if err = os.WriteFile(token, []byte("host-only-key"), 0600); err != nil {
		t.Fatal(err)
	}
	h := host{Endpoint: strings.TrimSpace(endpoint), TokenFile: token}
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
	stale := &provider{host: h, epoch: epoch, term: term}
	if err = stale.call(ctx, "list", "", nil, &result); err == nil {
		t.Fatal("stale host operation accepted")
	}
	stale.epoch = newer
	if err = stale.call(ctx, "list", "", nil, &result); err == nil {
		t.Fatal("old term matched the new generation")
	}
	current := &provider{host: h, epoch: newer, term: newTerm}
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
