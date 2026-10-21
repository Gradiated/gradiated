package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/virtual-kubelet/virtual-kubelet/errdefs"
	"github.com/virtual-kubelet/virtual-kubelet/node"
	v1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/fields"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/uuid"
	"k8s.io/client-go/informers"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/scheme"
	typedv1 "k8s.io/client-go/kubernetes/typed/core/v1"
	corelisters "k8s.io/client-go/listers/core/v1"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/tools/leaderelection"
	"k8s.io/client-go/tools/leaderelection/resourcelock"
	"k8s.io/client-go/tools/record"
	"k8s.io/client-go/util/workqueue"
)

type host struct {
	Runtimes   json.RawMessage `json:"-"`
	InstanceID string          `json:"instance_id"`
	Endpoint   string          `json:"endpoint"`
	TokenFile  string          `json:"token_file"`
	GPUCount   int64           `json:"gpu_count"`
	CPU        int64           `json:"cpu"`
	MemoryGiB  int64           `json:"memory_gib"`
	GPUProduct string          `json:"gpu_product"`
}
type configuration struct {
	HostBundle *hostBundle     `json:"host_bundle"`
	Runtimes   json.RawMessage `json:"runtimes"`
	Namespace  string          `json:"namespace"`
	Hosts      []host          `json:"hosts"`
}
type provider struct {
	host   host
	epoch  int64
	term   string
	source corelisters.PodLister
	client typedv1.CoreV1Interface
	mu     sync.Mutex
	pods   map[string]*v1.Pod
	node   *v1.Node
}

type statusPods struct{ typedv1.PodInterface }

func (p statusPods) UpdateStatus(ctx context.Context, pod *v1.Pod, _ metav1.UpdateOptions) (*v1.Pod, error) {
	// Transient provider failures must not complete restartPolicy: Never Jobs.
	if pod.Status.Reason == "ProviderFailed" && strings.HasPrefix(pod.Status.Message, "host temporarily unavailable:") {
		pod = pod.DeepCopy()
		pod.Status.Phase = v1.PodPending
		pod.Status.Reason = "WaitingForHost"
	}
	// Virtual Kubelet's full-object status writes also overwrite rollout annotations.
	patch, err := json.Marshal([]map[string]any{
		{"op": "test", "path": "/metadata/uid", "value": pod.UID},
		{"op": "add", "path": "/status", "value": pod.Status},
	})
	if err != nil {
		return nil, err
	}
	return p.Patch(ctx, pod.Name, types.JSONPatchType, patch, metav1.PatchOptions{}, "status")
}

type statusClient struct{ typedv1.CoreV1Interface }

func (c statusClient) Pods(namespace string) typedv1.PodInterface {
	return statusPods{c.CoreV1Interface.Pods(namespace)}
}

var hostClient = &http.Client{CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
	return fmt.Errorf("host redirects are unsupported")
}}

func retryHostOperation(_ context.Context, _ string, _ int, _ time.Time, err error) (*time.Duration, error) {
	if errdefs.IsInvalidInput(err) {
		return nil, err
	}
	delay := 10 * time.Second
	return &delay, nil
}

func (p *provider) call(ctx context.Context, operation string, uid string, pod *v1.Pod, result any) error {
	payload := map[string]any{"operation": operation, "uid": uid, "pod": pod, "epoch": p.epoch, "term": p.term}
	if operation == "configure" {
		payload["runtimes"] = p.host.Runtimes
	}
	return p.callPayload(ctx, payload, result)
}

func (p *provider) callPayload(ctx context.Context, payload map[string]any, result any) error {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	operation := payload["operation"]
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.host.Endpoint, bytes.NewReader(body))
	if err != nil {
		return err
	}
	token, err := os.ReadFile(p.host.TokenFile)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+strings.TrimSpace(string(token)))
	req.Header.Set("Content-Type", "application/json")
	response, err := hostClient.Do(req)
	if err != nil {
		return fmt.Errorf("host temporarily unavailable: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusNotFound {
		var failure struct {
			Error string `json:"error"`
		}
		if json.NewDecoder(io.LimitReader(response.Body, 1024)).Decode(&failure) == nil && failure.Error == "unknown_pod" {
			return errdefs.NotFoundf("host has no record of the pod for operation %s", operation)
		}
	}
	if response.StatusCode >= 500 {
		return fmt.Errorf("host temporarily unavailable: operation %s returned %d", operation, response.StatusCode)
	}
	if response.StatusCode != 200 {
		return errdefs.InvalidInputf("host operation %s returned %d", operation, response.StatusCode)
	}
	return json.NewDecoder(io.LimitReader(response.Body, 1024*1024)).Decode(result)
}
func (p *provider) CreatePod(ctx context.Context, pod *v1.Pod) error {
	original, err := p.source.Pods(pod.Namespace).Get(pod.Name)
	if err != nil {
		return err
	}
	pod = original.DeepCopy()
	if len(pod.Spec.Containers) != 1 || len(pod.Spec.Volumes) > 0 || len(pod.Spec.InitContainers) > 0 {
		return errdefs.InvalidInput("unsupported runtime pod")
	}
	container := pod.Spec.Containers[0]
	if len(container.Env) > 0 || len(container.EnvFrom) > 0 || len(container.Command) > 0 || len(container.Args) > 0 {
		return errdefs.InvalidInput("runtime overrides unsupported")
	}
	if len(p.host.Runtimes) > 0 {
		var staging map[string]any
		if err = p.call(ctx, "configure", "", nil, &staging); err != nil {
			return err
		}
	}
	var result map[string]any
	if err = p.call(ctx, "create", string(pod.UID), pod, &result); err != nil {
		return err
	}
	p.mu.Lock()
	p.pods[pod.Namespace+"/"+pod.Name] = pod
	p.mu.Unlock()
	return nil
}
func (p *provider) UpdatePod(ctx context.Context, pod *v1.Pod) error { return p.CreatePod(ctx, pod) }
func (p *provider) GetPod(_ context.Context, namespace, name string) (*v1.Pod, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	pod := p.pods[namespace+"/"+name]
	if pod == nil {
		return nil, errdefs.NotFound("pod not found")
	}
	return pod.DeepCopy(), nil
}
func (p *provider) GetPods(ctx context.Context) ([]*v1.Pod, error) {
	var pods []*v1.Pod
	if err := p.call(ctx, "list", "", nil, &pods); err != nil {
		return nil, err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, pod := range pods {
		p.pods[pod.Namespace+"/"+pod.Name] = pod
	}
	return pods, nil
}
func (p *provider) GetPodStatus(ctx context.Context, namespace, name string) (*v1.PodStatus, error) {
	pod, err := p.GetPod(ctx, namespace, name)
	if err != nil {
		return nil, err
	}
	var result struct {
		Running  bool `json:"running"`
		Ready    bool `json:"ready"`
		Draining bool `json:"draining"`
		Epoch    struct {
			PID   int    `json:"pid"`
			Birth string `json:"birth"`
		} `json:"epoch"`
	}
	err = p.call(ctx, "status", string(pod.UID), nil, &result)
	if errdefs.IsNotFound(err) {
		// The host answered but has lost the runtime, for example after a
		// re-image. Failing the pod lets its ReplicaSet replace it, as kubelet
		// does for an evicted pod.
		return &v1.PodStatus{Phase: v1.PodFailed, Reason: "RuntimeLost", Message: "The GPU host has no record of this pod",
			Conditions: []v1.PodCondition{{Type: v1.PodReady, Status: v1.ConditionFalse}, {Type: v1.ContainersReady, Status: v1.ConditionFalse}}}, nil
	}
	if err != nil {
		return &v1.PodStatus{Phase: v1.PodRunning, Reason: "HostUnreachable",
			Conditions: []v1.PodCondition{{Type: v1.PodReady, Status: v1.ConditionFalse}, {Type: v1.ContainersReady, Status: v1.ConditionFalse}}}, nil
	}
	status := &v1.PodStatus{Phase: v1.PodFailed, Reason: "RuntimeExited"}
	if pod.Spec.RestartPolicy != v1.RestartPolicyNever {
		status.Phase = v1.PodPending
		status.Reason = "RestartingRuntime"
	}
	if result.Running {
		ready := v1.ConditionFalse
		runtimeReady := v1.ConditionFalse
		if result.Ready {
			runtimeReady = v1.ConditionTrue
		}
		incarnation := fmt.Sprintf("runpod://%d:%s", result.Epoch.PID, result.Epoch.Birth)
		current, err := p.source.Pods(namespace).Get(name)
		qualified := err == nil && current.UID == pod.UID && current.Annotations["gradiated.com/qualified"] == "true" &&
			current.Annotations["gradiated.com/qualified-runtime"] == incarnation
		if result.Ready && (qualified || pod.Annotations["gradiated.com/workload-kind"] == "training") {
			ready = v1.ConditionTrue
		}
		status.Phase = v1.PodRunning
		status.Reason = ""
		status.Conditions = []v1.PodCondition{{Type: "RuntimeReady", Status: runtimeReady}, {Type: v1.PodReady, Status: ready}, {Type: v1.ContainersReady, Status: runtimeReady}, {Type: v1.PodInitialized, Status: v1.ConditionTrue}, {Type: v1.PodScheduled, Status: v1.ConditionTrue}}
		status.ContainerStatuses = []v1.ContainerStatus{{Name: pod.Spec.Containers[0].Name, Image: pod.Spec.Containers[0].Image, Ready: result.Ready, ContainerID: fmt.Sprintf("runpod://%d:%s", result.Epoch.PID, result.Epoch.Birth), State: v1.ContainerState{Running: &v1.ContainerStateRunning{}}}}
	}
	return status, nil
}
func (p *provider) DeletePod(ctx context.Context, pod *v1.Pod) error {
	for {
		var result struct {
			Deleted bool `json:"deleted"`
		}
		if err := p.call(ctx, "delete", string(pod.UID), pod, &result); err != nil {
			return err
		}
		if result.Deleted {
			p.mu.Lock()
			delete(p.pods, pod.Namespace+"/"+pod.Name)
			p.mu.Unlock()
			// Host cleanup completed the drain; Virtual Kubelet otherwise waits another grace period.
			zero := int64(0)
			uid := pod.UID
			err := p.client.Pods(pod.Namespace).Delete(ctx, pod.Name, metav1.DeleteOptions{
				GracePeriodSeconds: &zero, Preconditions: &metav1.Preconditions{UID: &uid},
			})
			if apierrors.IsNotFound(err) {
				return nil
			}
			return err
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(5 * time.Second):
		}
	}
}
func (p *provider) NotifyPods(ctx context.Context, callback func(*v1.Pod)) {
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				p.mu.Lock()
				pods := make([]*v1.Pod, 0, len(p.pods))
				for _, pod := range p.pods {
					pods = append(pods, pod.DeepCopy())
				}
				p.mu.Unlock()
				for _, pod := range pods {
					status, err := p.GetPodStatus(ctx, pod.Namespace, pod.Name)
					if err == nil {
						pod.Status = *status
						callback(pod)
					}
				}
			}
		}
	}()
}
func (p *provider) Ping(ctx context.Context) error {
	var result hostVersion
	if err := p.call(ctx, "ping", "", nil, &result); err != nil {
		return err
	}
	if result.InstanceID != p.host.InstanceID {
		return fmt.Errorf("host identity mismatch")
	}
	return nil
}
func (p *provider) NotifyNodeStatus(ctx context.Context, callback func(*v1.Node)) {
	go func() {
		ticker := time.NewTicker(10 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				copy := p.node.DeepCopy()
				ready := v1.ConditionTrue
				if p.Ping(ctx) != nil {
					ready = v1.ConditionFalse
				}
				copy.Status.Conditions = []v1.NodeCondition{{Type: v1.NodeReady, Status: ready, LastHeartbeatTime: metav1.Now(), LastTransitionTime: metav1.Now()}}
				callback(copy)
			}
		}
	}()
}

func runHost(ctx context.Context, client kubernetes.Interface, namespace string, h host, epoch int64, term string) error {
	name := "gpu-" + h.InstanceID
	if h.GPUCount == 0 {
		h.GPUCount = 1
	}
	if h.CPU == 0 {
		h.CPU = 16
	}
	if h.MemoryGiB == 0 {
		h.MemoryGiB = 64
	}
	if h.GPUProduct == "" {
		h.GPUProduct = "RTX-PRO-6000"
	}
	resources := v1.ResourceList{v1.ResourceCPU: *resource.NewQuantity(h.CPU, resource.DecimalSI), v1.ResourceMemory: resource.MustParse(fmt.Sprintf("%dGi", h.MemoryGiB)), v1.ResourcePods: resource.MustParse("16"), "nvidia.com/gpu": *resource.NewQuantity(h.GPUCount, resource.DecimalSI)}
	spec := &v1.Node{ObjectMeta: metav1.ObjectMeta{Name: name, Labels: map[string]string{"type": "virtual-kubelet", "kubernetes.io/hostname": name, "gradiated.com/provider": "runpod", "gradiated.com/instance-id": h.InstanceID, "nvidia.com/gpu.product": h.GPUProduct, "nvidia.com/gpu.count": fmt.Sprint(h.GPUCount)}},
		Spec:   v1.NodeSpec{Taints: []v1.Taint{{Key: "gradiated.com/gpu", Value: "true", Effect: v1.TaintEffectNoSchedule}}},
		Status: v1.NodeStatus{Capacity: resources, Allocatable: resources.DeepCopy(), NodeInfo: v1.NodeSystemInfo{OperatingSystem: "linux", Architecture: "amd64", KubeletVersion: "v1.33.5"}, Conditions: []v1.NodeCondition{{Type: v1.NodeReady, Status: v1.ConditionTrue, LastHeartbeatTime: metav1.Now(), LastTransitionTime: metav1.Now()}}}}
	factory := informers.NewSharedInformerFactoryWithOptions(client, time.Minute, informers.WithNamespace(namespace), informers.WithTweakListOptions(func(o *metav1.ListOptions) {
		o.FieldSelector = fields.OneTermEqualSelector("spec.nodeName", name).String()
	}))
	resourcesFactory := informers.NewSharedInformerFactoryWithOptions(client, time.Minute, informers.WithNamespace(namespace))
	pods := factory.Core().V1().Pods()
	p := &provider{host: h, epoch: epoch, term: term, source: pods.Lister(), client: client.CoreV1(), pods: map[string]*v1.Pod{}, node: spec}
	if err := p.Ping(ctx); err != nil {
		return err
	}
	broadcaster := record.NewBroadcaster()
	defer broadcaster.Shutdown()
	broadcaster.StartRecordingToSink(&typedv1.EventSinkImpl{Interface: client.CoreV1().Events(namespace)})
	pc, err := node.NewPodController(node.PodControllerConfig{PodClient: statusClient{client.CoreV1()}, PodInformer: pods, Provider: p,
		SyncPodsFromKubernetesRateLimiter:     workqueue.NewItemExponentialFailureRateLimiter(5*time.Second, 30*time.Second),
		SyncPodsFromKubernetesShouldRetryFunc: retryHostOperation,
		EventRecorder:                         broadcaster.NewRecorder(scheme.Scheme, v1.EventSource{Component: "runpod-kubelet", Host: name}),
		SecretInformer:                        resourcesFactory.Core().V1().Secrets(), ConfigMapInformer: resourcesFactory.Core().V1().ConfigMaps(), ServiceInformer: resourcesFactory.Core().V1().Services()})
	if err != nil {
		return err
	}
	nc, err := node.NewNodeController(p, spec, client.CoreV1().Nodes(), node.WithNodeEnableLeaseV1(client.CoordinationV1().Leases("kube-node-lease"), 40))
	if err != nil {
		return err
	}
	factory.Start(ctx.Done())
	resourcesFactory.Start(ctx.Done())
	go func() {
		if err := pc.Run(ctx, 2); err != nil && ctx.Err() == nil {
			log.Printf("pod controller %s failed: %v", name, err)
		}
	}()
	go func() {
		if err := nc.Run(ctx); err != nil && ctx.Err() == nil {
			log.Printf("node controller %s failed: %v", name, err)
		}
	}()
	select {
	case <-ctx.Done():
		return nil
	case <-pc.Done():
		return pc.Err()
	case <-nc.Done():
		return nc.Err()
	}
}

func checkQualification(selector string) error {
	config, err := rest.InClusterConfig()
	if err != nil {
		return err
	}
	client, err := kubernetes.NewForConfig(config)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Minute)
	defer cancel()
	for {
		pods, err := client.CoreV1().Pods("gpu-inference").List(ctx, metav1.ListOptions{LabelSelector: selector})
		if err != nil {
			return err
		}
		complete := len(pods.Items) > 0
		for _, pod := range pods.Items {
			incarnation := ""
			if len(pod.Status.ContainerStatuses) > 0 {
				incarnation = pod.Status.ContainerStatuses[0].ContainerID
			}
			if incarnation != "" && pod.Annotations["gradiated.com/qualification-error"] == incarnation {
				return fmt.Errorf("SDK qualification rejected pod %s", pod.Name)
			}
			ready := false
			for _, condition := range pod.Status.Conditions {
				if condition.Type == v1.PodReady && condition.Status == v1.ConditionTrue {
					ready = true
				}
			}
			if !ready || pod.DeletionTimestamp != nil || pod.Annotations["gradiated.com/qualified"] != "true" {
				complete = false
			}
		}
		if complete {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(5 * time.Second):
		}
	}
}

func main() {
	check := flag.String("check-qualification", "", "wait for SDK-qualified pods matching this selector")
	path := flag.String("config", "/etc/gpu-controller/hosts.json", "host configuration")
	flag.Parse()
	if *check != "" {
		if err := checkQualification(*check); err != nil {
			log.Fatal(err)
		}
		return
	}
	data, err := os.ReadFile(*path)
	if err != nil {
		log.Fatal(err)
	}
	var config configuration
	if err = json.Unmarshal(data, &config); err != nil {
		log.Fatal(err)
	}
	if config.Namespace != "gpu-inference" || len(config.Hosts) == 0 {
		log.Fatal("invalid GPU namespace or empty host list")
	}
	if err := config.HostBundle.validate(); err != nil {
		log.Fatal(err)
	}
	rollout := newHostRollout(config.HostBundle, config.Hosts)
	for index := range config.Hosts {
		config.Hosts[index].Runtimes = config.Runtimes
		h := config.Hosts[index]
		if h.GPUCount < 0 || h.GPUCount > 8 || h.CPU < 0 || h.CPU > 512 || h.MemoryGiB < 0 || h.MemoryGiB > 4096 {
			log.Fatal("invalid host resource capacity")
		}
		if h.Endpoint != "http://gpu-"+h.InstanceID+".tailscale-inference.svc.cluster.local:8888/_kubelet" {
			log.Fatal("host endpoint must use its private inference Service")
		}
	}
	var clientConfig *rest.Config
	if os.Getenv("KUBECONFIG") != "" {
		clientConfig, err = clientcmd.BuildConfigFromFlags("", os.Getenv("KUBECONFIG"))
	} else {
		clientConfig, err = rest.InClusterConfig()
	}
	if err != nil {
		log.Fatal(err)
	}
	client, err := kubernetes.NewForConfig(clientConfig)
	if err != nil {
		log.Fatal(err)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	go func() {
		http.HandleFunc("/metrics", rollout.metrics)
		http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) })
		server := &http.Server{Addr: ":9090", ReadHeaderTimeout: 5 * time.Second}
		if err := server.ListenAndServe(); err != nil {
			log.Printf("health server: %v", err)
			cancel()
		}
	}()
	identity := os.Getenv("POD_NAME")
	if identity == "" {
		identity = fmt.Sprintf("local-%d", os.Getpid())
	}
	lock := &resourcelock.LeaseLock{LeaseMeta: metav1.ObjectMeta{Name: "gpu-controller", Namespace: config.Namespace}, Client: client.CoordinationV1(), LockConfig: resourcelock.ResourceLockConfig{Identity: identity}}
	leaderelection.RunOrDie(ctx, leaderelection.LeaderElectionConfig{Lock: lock, LeaseDuration: 30 * time.Second, RenewDeadline: 20 * time.Second, RetryPeriod: 5 * time.Second, ReleaseOnCancel: true,
		Callbacks: leaderelection.LeaderCallbacks{
			OnStartedLeading: func(leader context.Context) {
				lease, err := client.CoordinationV1().Leases(config.Namespace).Get(leader, "gpu-controller", metav1.GetOptions{})
				if err != nil {
					log.Print(err)
					cancel()
					return
				}
				term := string(uuid.NewUUID())
				var group sync.WaitGroup
				group.Add(1)
				go func() { defer group.Done(); rollout.run(leader) }()
				for _, h := range config.Hosts {
					group.Add(1)
					go func(h host) {
						defer group.Done()
						var epoch int64
						for leader.Err() == nil {
							if epoch == 0 {
								var claimErr error
								epoch, claimErr = claimHost(leader, client, config.Namespace, identity, lease, term, h)
								if claimErr != nil {
									if errors.Is(claimErr, errLeadershipChanged) {
										cancel()
										return
									}
									log.Printf("host %s claim failed: %v", h.InstanceID, claimErr)
									select {
									case <-leader.Done():
										return
									case <-time.After(5 * time.Second):
										continue
									}
								}
							}
							rollout.register(&provider{host: h, epoch: epoch, term: term, client: client.CoreV1()})
							hostContext, stopHost := context.WithCancel(leader)
							err := runHost(hostContext, client, config.Namespace, h, epoch, term)
							stopHost()
							if err != nil {
								log.Printf("host %s controller failed: %v", h.InstanceID, err)
							}
							select {
							case <-leader.Done():
								return
							case <-time.After(5 * time.Second):
							}
						}
					}(h)
				}
				group.Wait()
			},
			OnStoppedLeading: func() { cancel() },
		},
	})
}
