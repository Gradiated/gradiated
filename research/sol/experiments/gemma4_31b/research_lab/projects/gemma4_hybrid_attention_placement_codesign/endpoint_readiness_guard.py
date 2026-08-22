#!/usr/bin/env python3
"""Liveness-aware non-generating readiness gate for a future endpoint owner."""
from __future__ import annotations
import argparse, json, os, subprocess, time

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--child-pid',type=int,required=True); p.add_argument('--container-state-command',required=True); p.add_argument('--health-command',required=True); p.add_argument('--deadline-seconds',type=float,required=True); p.add_argument('--poll-seconds',type=float,default=2); p.add_argument('--fatal-log-command')
    a=p.parse_args(); end=time.monotonic()+a.deadline_seconds
    while time.monotonic()<end:
        if not os.path.exists(f'/proc/{a.child_pid}'):
            raise RuntimeError('readiness_child_exited')
        state=subprocess.run(a.container_state_command,shell=True,text=True,capture_output=True)
        if state.returncode or state.stdout.strip()!='running':
            raise RuntimeError('readiness_container_not_running')
        if a.fatal_log_command:
            fatal=subprocess.run(a.fatal_log_command,shell=True,text=True,capture_output=True)
            if fatal.returncode==0 and fatal.stdout.strip():
                raise RuntimeError('readiness_fatal_log_marker')
        health=subprocess.run(a.health_command,shell=True,text=True,capture_output=True)
        if health.returncode==0:
            print(json.dumps({'ready':True,'child_pid':a.child_pid,'container':'running'})); return 0
        time.sleep(a.poll_seconds)
    raise RuntimeError('readiness_deadline_exceeded')
if __name__=='__main__': main()
