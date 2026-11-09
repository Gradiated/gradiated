package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"reflect"
	"strings"

	v1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/validation"
	typedv1 "k8s.io/client-go/kubernetes/typed/core/v1"
	"k8s.io/client-go/util/retry"
)

const managedExtraTaints = "gradiated.com/managed-extra-taints"

type hostTaint struct {
	Key    string         `json:"key"`
	Value  string         `json:"value"`
	Effect v1.TaintEffect `json:"effect"`
}

type hostTaints []hostTaint

func (taints *hostTaints) UnmarshalJSON(data []byte) error {
	if bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
		return fmt.Errorf("extraTaints must be a list")
	}
	var decoded []hostTaint
	var fields []map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return err
	}
	for _, item := range fields {
		if len(item) != 3 || item["key"] == nil || item["value"] == nil || item["effect"] == nil {
			return fmt.Errorf("extraTaints require explicit key, value and effect")
		}
		for _, value := range item {
			if bytes.Equal(bytes.TrimSpace(value), []byte("null")) {
				return fmt.Errorf("extraTaints fields must be strings")
			}
		}
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&decoded); err != nil {
		return err
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("invalid trailing extraTaints data")
	}
	if err := validateExtraTaints(decoded); err != nil {
		return err
	}
	*taints = decoded
	return nil
}

func validateExtraTaints(taints hostTaints) error {
	if len(taints) > 16 {
		return fmt.Errorf("extraTaints cannot exceed 16 reservations")
	}
	seen := map[string]bool{"gradiated.com/gpu": true}
	for _, taint := range taints {
		if len(validation.IsQualifiedName(taint.Key)) != 0 || len(validation.IsValidLabelValue(taint.Value)) != 0 ||
			taint.Effect != v1.TaintEffectNoSchedule || seen[taint.Key] ||
			strings.HasPrefix(taint.Key, "node.kubernetes.io/") || strings.HasPrefix(taint.Key, "node.cloudprovider.kubernetes.io/") {
			return fmt.Errorf("extraTaints require unique explicit key/value NoSchedule reservations")
		}
		seen[taint.Key] = true
	}
	return nil
}

func nodeTaints(h host) []v1.Taint {
	taints := []v1.Taint{{Key: "gradiated.com/gpu", Value: "true", Effect: v1.TaintEffectNoSchedule}}
	for _, taint := range h.ExtraTaints {
		taints = append(taints, v1.Taint{Key: taint.Key, Value: taint.Value, Effect: taint.Effect})
	}
	return taints
}

func reconcileNodeTaints(ctx context.Context, nodes typedv1.NodeInterface, h host) error {
	if err := validateExtraTaints(h.ExtraTaints); err != nil {
		return err
	}
	return retry.RetryOnConflict(retry.DefaultRetry, func() error {
		node, err := nodes.Get(ctx, "gpu-"+h.InstanceID, metav1.GetOptions{})
		if apierrors.IsNotFound(err) {
			return nil
		}
		if err != nil {
			return err
		}
		previous, tracked := node.Annotations[managedExtraTaints]
		if len(h.ExtraTaints) == 0 && !tracked {
			return nil
		}
		var old hostTaints
		if tracked {
			if err := json.Unmarshal([]byte(previous), &old); err != nil {
				return fmt.Errorf("invalid managed extra taints: %w", err)
			}
		}
		owned := map[string]bool{}
		for _, taint := range old {
			owned[taint.Key] = true
		}
		for _, taint := range h.ExtraTaints {
			owned[taint.Key] = true
		}
		updated := node.DeepCopy()
		updated.Spec.Taints = nil
		for _, taint := range node.Spec.Taints {
			if taint.Effect != v1.TaintEffectNoSchedule || (!owned[taint.Key] && taint.Key != "gradiated.com/gpu") {
				updated.Spec.Taints = append(updated.Spec.Taints, taint)
			}
		}
		updated.Spec.Taints = append(updated.Spec.Taints, nodeTaints(h)...)
		if updated.Annotations == nil {
			updated.Annotations = map[string]string{}
		}
		if len(h.ExtraTaints) == 0 {
			delete(updated.Annotations, managedExtraTaints)
		} else {
			encoded, _ := json.Marshal(h.ExtraTaints)
			updated.Annotations[managedExtraTaints] = string(encoded)
		}
		if reflect.DeepEqual(updated.Spec.Taints, node.Spec.Taints) && reflect.DeepEqual(updated.Annotations, node.Annotations) {
			return nil
		}
		_, err = nodes.Update(ctx, updated, metav1.UpdateOptions{})
		return err
	})
}
