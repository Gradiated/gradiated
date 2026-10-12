package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"reflect"
	"strings"
	"sync"
	"syscall"
	"time"

	dto "github.com/prometheus/client_model/go"
	"github.com/virtual-kubelet/virtual-kubelet/errdefs"
	"github.com/virtual-kubelet/virtual-kubelet/node"
	"github.com/virtual-kubelet/virtual-kubelet/node/api"
	"github.com/virtual-kubelet/virtual-kubelet/node/api/statsv1alpha1"
	"github.com/virtual-kubelet/virtual-kubelet/node/nodeutil"
	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	corev1listers "k8s.io/client-go/listers/core/v1"
	"k8s.io/client-go/tools/clientcmd"
)

type provider struct {
	host, port, key, knownHosts, script string
	mu                                  sync.Mutex
	pods                                map[string]*v1.Pod
	source                              corev1listers.PodLister
	gpuCount                            int
}

func (p *provider) remote(ctx context.Context, op string, request any, result any) error {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	body, err := json.Marshal(request)
	if err != nil {
		return err
	}
	cmd := exec.CommandContext(ctx, "ssh", "-i", p.key, "-p", p.port,
		"-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
		"-o", "UserKnownHostsFile="+p.knownHosts, "root@"+p.host, "python3 "+p.script+" "+op)
	cmd.Stdin = bytes.NewReader(body)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	output, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("remote %s: %w: %s", op, err, stderr.String())
	}
	return json.Unmarshal(output, result)
}

func validate(pod *v1.Pod) error {
	if pod.Namespace != "vk-trial" || len(pod.Spec.Containers) != 1 || len(pod.Spec.InitContainers) > 0 || len(pod.Spec.Volumes) > 0 || pod.Spec.HostNetwork || pod.Spec.HostPID || pod.Spec.HostIPC || (pod.Spec.SecurityContext != nil && !reflect.DeepEqual(*pod.Spec.SecurityContext, v1.PodSecurityContext{})) {
		return errdefs.InvalidInput("only isolated vk-trial smoke pods are supported")
	}
	c := pod.Spec.Containers[0]
	if (c.Image != "gradiated/vk-smoke:process-v1" && c.Image != "gradiated/vk-gpu-smoke:process-v1") || len(c.Command) > 0 || len(c.Args) > 0 || len(c.Env) > 0 || len(c.EnvFrom) > 0 || c.SecurityContext != nil || len(c.Ports) > 0 || c.ReadinessProbe != nil || c.LivenessProbe != nil || c.StartupProbe != nil {
		return errdefs.InvalidInput("unsupported container configuration")
	}
	limit := c.Resources.Limits[v1.ResourceName("nvidia.com/gpu")]
	request := c.Resources.Requests[v1.ResourceName("nvidia.com/gpu")]
	whole, exact := limit.AsInt64()
	if c.Image == "gradiated/vk-smoke:process-v1" && (limit.Sign() != 0 || request.Sign() != 0) {
		return errdefs.InvalidInput("CPU smoke cannot request GPUs")
	}
	if c.Image == "gradiated/vk-gpu-smoke:process-v1" && (!exact || whole < 1 || whole > 4 || limit.Cmp(request) != 0) {
		return errdefs.InvalidInput("GPU smoke requires one to four whole GPUs")
	}
	return nil
}

func (p *provider) CreatePod(ctx context.Context, pod *v1.Pod) error {
	original, err := p.source.Pods(pod.Namespace).Get(pod.Name)
	if err != nil {
		return err
	}
	pod = original.DeepCopy()
	if err := validate(pod); err != nil {
		return err
	}
	var result map[string]any
	count := pod.Spec.Containers[0].Resources.Limits[v1.ResourceName("nvidia.com/gpu")]
	if count.Value() > int64(p.gpuCount) {
		return errdefs.InvalidInput("GPU smoke exceeds enabled capacity")
	}
	if err := p.remote(ctx, "create", map[string]any{"uid": pod.UID, "pod": pod, "gpu_count": count.Value()}, &result); err != nil {
		return err
	}
	p.mu.Lock()
	p.pods[pod.Namespace+"/"+pod.Name] = pod.DeepCopy()
	p.mu.Unlock()
	return nil
}
func (p *provider) UpdatePod(ctx context.Context, pod *v1.Pod) error { return p.CreatePod(ctx, pod) }
func (p *provider) GetPod(_ context.Context, ns, name string) (*v1.Pod, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	pod := p.pods[ns+"/"+name]
	if pod == nil {
		return nil, errdefs.NotFound("pod not found")
	}
	return pod.DeepCopy(), nil
}
func (p *provider) GetPods(ctx context.Context) ([]*v1.Pod, error) {
	var pods []*v1.Pod
	if err := p.remote(ctx, "list", map[string]any{}, &pods); err != nil {
		return nil, err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, pod := range pods {
		p.pods[pod.Namespace+"/"+pod.Name] = pod.DeepCopy()
	}
	return pods, nil
}
func (p *provider) DeletePod(ctx context.Context, pod *v1.Pod) error {
	var result map[string]any
	if err := p.remote(ctx, "delete", map[string]any{"uid": pod.UID}, &result); err != nil {
		return err
	}
	p.mu.Lock()
	delete(p.pods, pod.Namespace+"/"+pod.Name)
	p.mu.Unlock()
	return nil
}
func (p *provider) GetPodStatus(ctx context.Context, ns, name string) (*v1.PodStatus, error) {
	pod, err := p.GetPod(ctx, ns, name)
	if err != nil {
		return nil, err
	}
	var result struct {
		Running bool `json:"running"`
		Ready   bool `json:"ready"`
	}
	if err = p.remote(ctx, "status", map[string]any{"uid": pod.UID}, &result); err != nil {
		return nil, err
	}
	status := &v1.PodStatus{Phase: v1.PodFailed, Reason: "ProcessExited"}
	if result.Running {
		status.Phase = v1.PodRunning
		status.Reason = ""
		ready := v1.ConditionFalse
		if result.Ready {
			ready = v1.ConditionTrue
		}
		status.Conditions = []v1.PodCondition{{Type: v1.PodReady, Status: ready}, {Type: v1.ContainersReady, Status: ready}, {Type: v1.PodInitialized, Status: v1.ConditionTrue}, {Type: v1.PodScheduled, Status: v1.ConditionTrue}}
		status.ContainerStatuses = []v1.ContainerStatus{{Name: pod.Spec.Containers[0].Name, Ready: result.Ready, Image: pod.Spec.Containers[0].Image, State: v1.ContainerState{Running: &v1.ContainerStateRunning{StartedAt: metav1.Now()}}}}
	}
	return status, nil
}
func (p *provider) NotifyPods(ctx context.Context, cb func(*v1.Pod)) {
	go func() {
		ticker := time.NewTicker(2 * time.Second)
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
						cb(pod)
					}
				}
			}
		}
	}()
}
func (p *provider) GetContainerLogs(ctx context.Context, ns, name, container string, _ api.ContainerLogOpts) (io.ReadCloser, error) {
	pod, err := p.GetPod(ctx, ns, name)
	if err != nil {
		return nil, err
	}
	var result struct {
		Logs string `json:"logs"`
	}
	err = p.remote(ctx, "logs", map[string]any{"uid": pod.UID}, &result)
	return io.NopCloser(strings.NewReader(result.Logs)), err
}
func (p *provider) RunInContainer(context.Context, string, string, string, []string, api.AttachIO) error {
	return errdefs.InvalidInput("exec unsupported")
}
func (p *provider) AttachToContainer(context.Context, string, string, string, api.AttachIO) error {
	return errdefs.InvalidInput("attach unsupported")
}
func (p *provider) GetStatsSummary(context.Context) (*statsv1alpha1.Summary, error) {
	return nil, errdefs.InvalidInput("metrics unsupported")
}
func (p *provider) GetMetricsResource(context.Context) ([]*dto.MetricFamily, error) {
	return nil, errdefs.InvalidInput("metrics unsupported")
}
func (p *provider) PortForward(context.Context, string, string, int32, io.ReadWriteCloser) error {
	return errdefs.InvalidInput("port forward unsupported")
}

func main() {
	p := &provider{pods: map[string]*v1.Pod{}}
	flag.StringVar(&p.host, "host", "", "pinned SSH host")
	flag.StringVar(&p.port, "port", "22", "SSH port")
	flag.StringVar(&p.key, "key", "", "SSH key file")
	flag.StringVar(&p.knownHosts, "known-hosts", "", "pinned known hosts file")
	flag.StringVar(&p.script, "script", "", "absolute remote helper path")
	flag.IntVar(&p.gpuCount, "gpu-smoke-count", 0, "GPU discovery capacity on an idle host, zero disables")
	flag.Parse()
	if p.gpuCount < 0 || p.gpuCount > 4 {
		log.Fatal("GPU smoke count must be between zero and four")
	}
	config, err := clientcmd.BuildConfigFromFlags("", os.Getenv("KUBECONFIG"))
	if err != nil {
		log.Fatal("an isolated local kubeconfig is required")
	}
	endpoint, err := url.Parse(config.Host)
	if err != nil || endpoint.Scheme != "https" || endpoint.Hostname() != "127.0.0.1" {
		log.Fatal("prototype only supports a loopback Kubernetes API")
	}
	if p.host == "" || p.key == "" || p.knownHosts == "" || !strings.HasPrefix(p.script, "/tmp/gradiated-vk-") || strings.ContainsAny(p.script, " \t\n;'\"`$") {
		log.Fatal("invalid SSH configuration")
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	ctx, timeout := context.WithTimeout(ctx, 25*time.Minute)
	defer timeout()
	n, err := nodeutil.NewNode("runpod-prototype", func(cfg nodeutil.ProviderConfig) (nodeutil.Provider, node.NodeProvider, error) {
		p.source = cfg.Pods
		cfg.Node.Spec.Taints = []v1.Taint{{Key: "gradiated.com/vk-trial", Value: "true", Effect: v1.TaintEffectNoSchedule}}
		cfg.Node.Status.Capacity = v1.ResourceList{v1.ResourceCPU: resource.MustParse("2"), v1.ResourceMemory: resource.MustParse("1Gi"), v1.ResourcePods: resource.MustParse("8")}
		if p.gpuCount > 0 {
			cfg.Node.Status.Capacity[v1.ResourceName("nvidia.com/gpu")] = *resource.NewQuantity(int64(p.gpuCount), resource.DecimalSI)
		}
		cfg.Node.Status.Allocatable = cfg.Node.Status.Capacity.DeepCopy()
		cfg.Node.Status.NodeInfo = v1.NodeSystemInfo{OperatingSystem: "linux", Architecture: "amd64", KubeletVersion: "v1.33.5"}
		return p, nil, nil
	})
	if err != nil {
		log.Fatal(err)
	}
	if err = n.Run(ctx); err != nil && ctx.Err() == nil {
		log.Fatal(err)
	}
}
