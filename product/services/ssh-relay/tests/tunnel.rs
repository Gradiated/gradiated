//! Run explicitly after building the integration image. No cloud access.
use std::{
    fs,
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    path::Path,
    process::{Child, Command, Output, Stdio},
    thread::sleep,
    time::{Duration, Instant},
};

const DEST: &str = "nomad-0.nomad-headless.nomad.svc.cluster.local:4647";

fn output(command: &mut Command) -> Output {
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let end = Instant::now() + Duration::from_secs(20);
    loop {
        if child.try_wait().unwrap().is_some() {
            return child.wait_with_output().unwrap();
        }
        if Instant::now() >= end {
            let _ = child.kill();
            let _ = child.wait();
            panic!("Test command timed out");
        }
        sleep(Duration::from_millis(20));
    }
}
fn checked(command: &mut Command) -> String {
    let result = output(command);
    assert!(
        result.status.success(),
        "Test command failed: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    String::from_utf8(result.stdout).unwrap()
}
struct Fixture {
    name: String,
    children: Vec<Child>,
    root: tempfile::TempDir,
}
impl Drop for Fixture {
    fn drop(&mut self) {
        // Keep temporary keys alive until all clients and the container stop.
        for child in &mut self.children {
            let _ = child.kill();
            let _ = child.wait();
        }
        let _ = output(Command::new("docker").args(["rm", "-f", &self.name]));
    }
}
fn publish(root: &Path, content: &str) {
    fs::write(root.join("access/next.json"), content).unwrap();
    fs::rename(
        root.join("access/next.json"),
        root.join("access/instances.json"),
    )
    .unwrap();
}
fn echo(stream: &mut TcpStream) -> bool {
    let mut received = [0; 4];
    stream.write_all(b"test").is_ok()
        && stream.read_exact(&mut received).is_ok()
        && received == *b"test"
}
fn connect(port: u16) -> TcpStream {
    let end = Instant::now() + Duration::from_secs(15);
    while Instant::now() < end {
        if let Ok(mut stream) =
            TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_secs(1))
        {
            stream
                .set_read_timeout(Some(Duration::from_secs(1)))
                .unwrap();
            stream
                .set_write_timeout(Some(Duration::from_secs(1)))
                .unwrap();
            if echo(&mut stream) {
                return stream;
            }
        }
        sleep(Duration::from_millis(100));
    }
    panic!("Forwarded echo did not become ready");
}
fn ssh(root: &Path, port: &str, index: usize) -> Command {
    let mut command = Command::new("ssh");
    command.args([
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=3",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        &format!("UserKnownHostsFile={}", root.join("known_hosts").display()),
        "-i",
        root.join(index.to_string()).to_str().unwrap(),
        "-p",
        port,
    ]);
    command
}
fn user(index: usize) -> String {
    format!(
        "ni_{}@127.0.0.1",
        if index == 0 {
            "111111111111111111111111"
        } else {
            "222222222222222222222222"
        }
    )
}

#[test]
#[ignore = "requires Docker integration image and local OpenSSH; see README"]
fn restricts_access_and_revokes_active_tunnels() {
    let root = tempfile::tempdir().unwrap();
    let name = format!(
        "ssh-relay-{}",
        root.path()
            .file_name()
            .unwrap()
            .to_str()
            .unwrap()
            .replace('.', "")
    );
    let mut fixture = Fixture {
        name,
        children: Vec::new(),
        root,
    };
    let root = fixture.root.path().to_path_buf();
    for dir in ["access", "hostkeys"] {
        fs::create_dir(root.join(dir)).unwrap();
    }
    for key in ["hostkeys/ssh_host_ed25519_key", "0", "1"] {
        checked(
            Command::new("ssh-keygen")
                .args(["-q", "-t", "ed25519", "-N", "", "-f"])
                .arg(root.join(key)),
        );
    }
    let records: Vec<_> = (0..2).map(|index| {
        let key = fs::read_to_string(root.join(format!("{index}.pub"))).unwrap();
        serde_json::json!({"instance_id": if index == 0 {"11111111-1111-1111-1111-111111111111"} else {"22222222-2222-2222-2222-222222222222"}, "public_key": key.split_whitespace().take(2).collect::<Vec<_>>().join(" ")})
    }).collect();
    publish(&root, &serde_json::to_string(&records).unwrap());
    checked(Command::new("docker").args([
        "run",
        "-d",
        "--name",
        &fixture.name,
        "--platform",
        "linux/amd64",
        "--add-host",
        "nomad-0.nomad-headless.nomad.svc.cluster.local:127.0.0.1",
        "-p",
        "127.0.0.1::2222",
        "-v",
        &format!("{}:/access:ro", root.join("access").display()),
        "-v",
        &format!("{}:/host-keys:ro", root.join("hostkeys").display()),
        "gradiated/ssh-relay:test",
    ]));
    let mapped = checked(Command::new("docker").args(["port", &fixture.name, "2222/tcp"]));
    let port = mapped.trim().rsplit(':').next().unwrap();
    fs::write(
        root.join("known_hosts"),
        format!(
            "[127.0.0.1]:{port} {}",
            fs::read_to_string(root.join("hostkeys/ssh_host_ed25519_key.pub")).unwrap()
        ),
    )
    .unwrap();
    fixture.children.push(
        Command::new("docker")
            .args(["exec", &fixture.name, "/usr/local/bin/test-echo"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    );
    sleep(Duration::from_secs(2));
    let mut streams = Vec::new();
    for index in 0..2 {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let local = listener.local_addr().unwrap().port();
        drop(listener);
        fixture.children.push(
            ssh(&root, port, index)
                .args([
                    "-NT",
                    "-L",
                    &format!("127.0.0.1:{local}:{DEST}"),
                    &user(index),
                ])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap(),
        );
        streams.push(connect(local));
    }
    assert!(
        !output(ssh(&root, port, 0).args([&user(0), "true"]))
            .status
            .success(),
        "Shell was accepted"
    );
    assert!(
        !output(ssh(&root, port, 0).args(["-W", "127.0.0.1:22", &user(0)]))
            .status
            .success(),
        "Undeclared destination was accepted"
    );
    publish(&root, &serde_json::to_string(&records[1..]).unwrap());
    let end = Instant::now() + Duration::from_secs(8);
    while echo(&mut streams[0]) {
        assert!(Instant::now() < end, "Revoked connection remained open");
        sleep(Duration::from_millis(100));
    }
    assert!(
        echo(&mut streams[1]),
        "Revocation interrupted another instance"
    );
    assert!(
        !output(ssh(&root, port, 0).args(["-W", DEST, &user(0)]))
            .status
            .success(),
        "Revoked key reconnected"
    );
    publish(&root, "{");
    let end = Instant::now() + Duration::from_secs(8);
    while checked(Command::new("docker").args([
        "inspect",
        "--format",
        "{{.State.Running}}",
        &fixture.name,
    ]))
    .trim()
        != "false"
    {
        assert!(
            Instant::now() < end,
            "Invalid inventory left the relay running"
        );
        sleep(Duration::from_millis(100));
    }
    assert!(
        !echo(&mut streams[1]),
        "Invalid inventory left a tunnel open"
    );
}
