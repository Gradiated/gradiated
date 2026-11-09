package main

import (
	"context"
	"encoding/json"
	"fmt"
	"reflect"
	"testing"

	v1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"
)

func kimiReservation() hostTaints {
	return hostTaints{{Key: "gradiated.com/kimi-k31", Value: "reserved", Effect: v1.TaintEffectNoSchedule}}
}

func TestGpuHostExtraTaintsReachTheNodeCreationSpec(t *testing.T) {
	object := gpuHostObject(first, 8)
	object.Object["spec"].(map[string]any)["extraTaints"] = []any{map[string]any{
		"key": "gradiated.com/kimi-k31", "value": "reserved", "effect": "NoSchedule"}}
	h, err := hostFromObject(object.Object)
	if err != nil || !reflect.DeepEqual(h.ExtraTaints, kimiReservation()) {
		t.Fatalf("host %+v, err %v", h, err)
	}
	created := nodeTaints(h)
	if len(created) != 2 || created[0].Key != "gradiated.com/gpu" || created[1].Key != "gradiated.com/kimi-k31" {
		t.Fatalf("node creation taints = %+v", created)
	}
	encoded, err := json.Marshal(h)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	_ = json.Unmarshal(encoded, &config)
	if len(config["extra_taints"].([]any)) != 1 {
		t.Fatalf("serialized host = %s", encoded)
	}
	h.ExtraTaints = nil
	encoded, _ = json.Marshal(h)
	_ = json.Unmarshal(encoded, &config)
	var plain map[string]any
	_ = json.Unmarshal(encoded, &plain)
	if _, exists := plain["extra_taints"]; exists || len(nodeTaints(h)) != 1 {
		t.Fatalf("default host gained reservations: %s", encoded)
	}
}

func TestExtraTaintsRejectInvalidOrBroadConfiguration(t *testing.T) {
	tooMany := make(hostTaints, 17)
	for i := range tooMany {
		tooMany[i] = hostTaint{Key: fmt.Sprintf("example.com/reservation-%d", i), Value: "reserved", Effect: v1.TaintEffectNoSchedule}
	}
	if err := validateExtraTaints(tooMany); err == nil {
		t.Fatal("accepted more reservations than the CRD allows")
	}
	for _, raw := range []string{
		`null`, `{}`, `[null]`, `[{}]`,
		`[{"key":"gradiated.com/kimi-k31","effect":"NoSchedule"}]`,
		`[{"key":"gradiated.com/kimi-k31","value":null,"effect":"NoSchedule"}]`,
		`[{"key":"gradiated.com/kimi-k31","value":"reserved","effect":"NoExecute"}]`,
		`[{"key":"gradiated.com/gpu","value":"false","effect":"NoSchedule"}]`,
		`[{"key":"node.kubernetes.io/not-ready","value":"","effect":"NoSchedule"}]`,
		`[{"key":"a/b/c","value":"reserved","effect":"NoSchedule"}]`,
		`[{"key":"valid","value":"bad value","effect":"NoSchedule"}]`,
		`[{"key":"valid","value":"a","effect":"NoSchedule","operator":"Exists"}]`,
		`[{"key":"valid","value":"a","effect":"NoSchedule"},{"key":"valid","value":"b","effect":"NoSchedule"}]`,
	} {
		t.Run(raw, func(t *testing.T) {
			var taints hostTaints
			if err := json.Unmarshal([]byte(raw), &taints); err == nil {
				t.Fatalf("accepted %s", raw)
			}
		})
	}
}

func TestReservationReconciliationPreservesOtherTaintsAndNodeFields(t *testing.T) {
	ctx := context.Background()
	name := "gpu-" + first
	unrelated := []v1.Taint{
		{Key: "node.kubernetes.io/not-ready", Effect: v1.TaintEffectNoSchedule},
		{Key: "node.kubernetes.io/not-ready", Effect: v1.TaintEffectNoExecute},
		{Key: "other.example/reserved", Value: "other", Effect: v1.TaintEffectNoSchedule},
	}
	original := &v1.Node{ObjectMeta: metav1.ObjectMeta{Name: name, Labels: map[string]string{"keep": "yes"},
		Annotations: map[string]string{"keep": "yes"}}, Spec: v1.NodeSpec{Unschedulable: true,
		Taints: append(nodeTaints(host{}), unrelated...)}}
	client := fake.NewSimpleClientset(original)
	h := host{InstanceID: first, ExtraTaints: kimiReservation()}
	if err := reconcileNodeTaints(ctx, client.CoreV1().Nodes(), h); err != nil {
		t.Fatal(err)
	}
	updated, _ := client.CoreV1().Nodes().Get(ctx, name, metav1.GetOptions{})
	want := append(append([]v1.Taint{}, unrelated...), nodeTaints(h)...)
	if !reflect.DeepEqual(updated.Spec.Taints, want) || !updated.Spec.Unschedulable ||
		updated.Labels["keep"] != "yes" || updated.Annotations["keep"] != "yes" || updated.Annotations[managedExtraTaints] == "" {
		t.Fatalf("reservation changed unrelated node state: %+v", updated)
	}
	client.ClearActions()
	if err := reconcileNodeTaints(ctx, client.CoreV1().Nodes(), h); err != nil {
		t.Fatal(err)
	}
	for _, action := range client.Actions() {
		if action.GetVerb() != "get" {
			t.Fatalf("unchanged reservation wrote the Node: %v", action)
		}
	}
	updated.Spec.Taints = updated.Spec.Taints[:len(updated.Spec.Taints)-1]
	_, _ = client.CoreV1().Nodes().Update(ctx, updated, metav1.UpdateOptions{})
	if err := reconcileNodeTaints(ctx, client.CoreV1().Nodes(), h); err != nil {
		t.Fatal(err)
	}
	repaired, _ := client.CoreV1().Nodes().Get(ctx, name, metav1.GetOptions{})
	if !reflect.DeepEqual(repaired.Spec.Taints, want) {
		t.Fatalf("reservation drift was not restored: %+v", repaired.Spec.Taints)
	}
	h.ExtraTaints = nil
	if err := reconcileNodeTaints(ctx, client.CoreV1().Nodes(), h); err != nil {
		t.Fatal(err)
	}
	removed, _ := client.CoreV1().Nodes().Get(ctx, name, metav1.GetOptions{})
	if !reflect.DeepEqual(removed.Spec.Taints, append(unrelated, nodeTaints(host{})...)) ||
		removed.Annotations[managedExtraTaints] != "" || removed.Annotations["keep"] != "yes" {
		t.Fatalf("reservation removal changed unrelated taints: %+v", removed)
	}
}

func TestUnreservedHostDoesNotChangeExistingNodeTaints(t *testing.T) {
	ctx := context.Background()
	original := &v1.Node{ObjectMeta: metav1.ObjectMeta{Name: "gpu-" + first},
		Spec: v1.NodeSpec{Taints: []v1.Taint{{Key: "custom", Value: "keep", Effect: v1.TaintEffectNoSchedule}}}}
	client := fake.NewSimpleClientset(original)
	if err := reconcileNodeTaints(ctx, client.CoreV1().Nodes(), host{InstanceID: first}); err != nil {
		t.Fatal(err)
	}
	for _, action := range client.Actions() {
		if action.GetVerb() != "get" {
			t.Fatalf("unreserved host wrote the Node: %v", action)
		}
	}
	if err := reconcileNodeTaints(ctx, client.CoreV1().Nodes(), host{InstanceID: second, ExtraTaints: kimiReservation()}); err != nil {
		t.Fatalf("missing Node must be created later with reservation: %v", err)
	}
}

func TestReservationConflictRetriesFromFreshNodeState(t *testing.T) {
	ctx := context.Background()
	name := "gpu-" + first
	client := fake.NewSimpleClientset(&v1.Node{ObjectMeta: metav1.ObjectMeta{Name: name}})
	updates := 0
	client.PrependReactor("update", "nodes", func(k8stesting.Action) (bool, runtime.Object, error) {
		updates++
		if updates == 1 {
			resource := schema.GroupVersionResource{Version: "v1", Resource: "nodes"}
			current, err := client.Tracker().Get(resource, "", name)
			if err != nil {
				t.Fatal(err)
			}
			changed := current.(*v1.Node).DeepCopy()
			changed.Spec.Taints = append(changed.Spec.Taints, v1.Taint{Key: "node.kubernetes.io/not-ready", Effect: v1.TaintEffectNoExecute})
			if err := client.Tracker().Update(resource, changed, ""); err != nil {
				t.Fatal(err)
			}
			return true, nil, apierrors.NewConflict(schema.GroupResource{Resource: "nodes"}, name, fmt.Errorf("changed"))
		}
		return false, nil, nil
	})
	if err := reconcileNodeTaints(ctx, client.CoreV1().Nodes(), host{InstanceID: first, ExtraTaints: kimiReservation()}); err != nil {
		t.Fatal(err)
	}
	if updates != 2 {
		t.Fatalf("updates = %d, want conflict retry", updates)
	}
	final, _ := client.CoreV1().Nodes().Get(ctx, name, metav1.GetOptions{})
	if len(final.Spec.Taints) != 3 || final.Spec.Taints[0].Key != "node.kubernetes.io/not-ready" {
		t.Fatalf("conflict retry lost a concurrent lifecycle taint: %+v", final.Spec.Taints)
	}
}
