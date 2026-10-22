from dataclasses import dataclass
import ipaddress
from pathlib import Path
import pwd

# Accounts created by the GPU base image.
DOWNLOADER = 'downloader'
DESMOND = 'desmond'
TAILSCALE = 'tailscale'

AGENT_PORT = 8887  # host agent API, loopback only
SERVE_PORT = 8888  # the only port Tailscale serves to the tailnet
PROXY_PORT = 8889  # host agent proxy behind Tailscale serve
CONTROL_PORT = 3004  # loopback bridge to the control API for runtime download grants

TAILNET = ipaddress.ip_network('100.64.0.0/10')
TAILNET_DOMAIN = 'tail186117.ts.net'


@dataclass(frozen=True)
class Layout:

    root: Path = Path('/')

    def _path(self, value):
        return self.root / value.lstrip('/')

    def account(self, name):
        entry = pwd.getpwnam(name)
        return entry.pw_uid, entry.pw_gid

    @property
    def etc(self):
        return self._path('/etc/gradiated')

    @property
    def base_id(self):
        return self.etc / 'base-id'

    @property
    def config(self):
        return self.etc / 'kubelet.json'

    @property
    def management_token(self):
        return self.etc / 'kubelet-management.token'

    @property
    def runtime_token(self):
        return self.etc / 'runtime-access.token'

    @property
    def tailscale_config(self):
        return self.etc / 'tailscale.json'

    @property
    def control_config(self):
        return self.etc / 'tailscale-control.json'

    @property
    def state(self):
        return self._path('/var/lib/gradiated-kubelet')

    @property
    def install(self):
        return self._path('/opt/gradiated/kubelet')

    @property
    def tailscale_state(self):
        return self._path('/var/lib/gradiated-tailscale')

    @property
    def tailscale_bin(self):
        return self._path('/opt/gradiated/tailscale')

    @property
    def logs(self):
        return self._path('/var/log')

    @property
    def cgroup(self):
        return self._path('/sys/fs/cgroup')

    @property
    def meminfo(self):
        return self._path('/proc/meminfo')
