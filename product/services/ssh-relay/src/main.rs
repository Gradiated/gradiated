use base64::{engine::general_purpose::STANDARD, Engine};
use serde::Deserialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{self, Read},
    os::unix::fs::PermissionsExt,
    path::Path,
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::{Duration, Instant},
};
use uuid::Uuid;

type Inventory = BTreeMap<String, String>;
const KEYS: &str = "/run/nomad-tunnel-keys";
const CONFIG: &str = "/etc/ssh/nomad-tunnel.conf";
const MAX_BYTES: u64 = 4 * 1024 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Instance {
    instance_id: Uuid,
    public_key: String,
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::other(message)
}

fn inventory(raw: &[u8]) -> io::Result<Inventory> {
    if raw.len() as u64 > MAX_BYTES {
        return Err(invalid("Access inventory exceeds size limit"));
    }
    let rows: Vec<Instance> =
        serde_json::from_slice(raw).map_err(|_| invalid("Invalid access inventory"))?;
    if rows.len() > 10_000 {
        return Err(invalid("Too many instances"));
    }
    let mut result = Inventory::new();
    let mut keys = BTreeSet::new();
    for row in rows {
        let user = format!("ni_{}", &row.instance_id.simple().to_string()[..24]);
        let parts: Vec<_> = row.public_key.split_whitespace().collect();
        if parts.len() != 2 || parts[0] != "ssh-ed25519" || parts[1].len() > 200 {
            return Err(invalid("Expected an Ed25519 public key without options"));
        }
        let blob = STANDARD
            .decode(parts[1])
            .map_err(|_| invalid("Invalid public key"))?;
        if blob.len() != 51 || !blob.starts_with(b"\0\0\0\x0bssh-ed25519\0\0\0\x20") {
            return Err(invalid("Invalid Ed25519 public key"));
        }
        if !keys.insert(blob) || result.insert(user, parts.join(" ")).is_some() {
            return Err(invalid("Duplicate instance account or public key"));
        }
    }
    Ok(result)
}

fn read_inventory() -> io::Result<Inventory> {
    let mut raw = Vec::new();
    fs::File::open("/access/instances.json")?
        .take(MAX_BYTES + 1)
        .read_to_end(&mut raw)?;
    inventory(&raw)
}

// Bound system commands. Do not log their output: it can contain key material.
fn command(program: &str, args: &[&str], accepted: &[i32]) -> io::Result<()> {
    let mut child = Command::new(program)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if let Some(status) = child.try_wait()? {
            return if status.code().is_some_and(|code| accepted.contains(&code)) {
                Ok(())
            } else {
                Err(invalid("System command failed"))
            };
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(invalid("System command timed out"));
        }
        thread::sleep(Duration::from_millis(20));
    }
}

fn remove_key(user: &str) -> io::Result<()> {
    match fs::remove_file(Path::new(KEYS).join(user)) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        result => result,
    }
}

fn revoke(user: &str) -> io::Result<()> {
    // Attempt both operations even when key removal fails.
    let removed = remove_key(user);
    let killed = command("pkill", &["-KILL", "-u", user], &[0, 1]);
    removed.and(killed)
}

fn sync(previous: &Inventory, desired: &Inventory, owned: &mut BTreeSet<String>) -> io::Result<()> {
    for (user, key) in previous {
        if desired.get(user) != Some(key) {
            revoke(user)?;
        }
    }
    for (user, key) in desired {
        if !owned.contains(user) {
            // useradd fails on any existing account. Never adopt an unrelated account.
            command(
                "useradd",
                &[
                    "--no-create-home",
                    "--shell",
                    "/usr/sbin/nologin",
                    "--password",
                    "*",
                    user,
                ],
                &[0],
            )?;
            owned.insert(user.clone());
        }
        if previous.get(user) != Some(key) {
            let temp = Path::new(KEYS).join(format!("{user}.new"));
            fs::write(&temp, format!("restrict,port-forwarding {key}\n"))?;
            fs::set_permissions(&temp, fs::Permissions::from_mode(0o644))?;
            fs::rename(temp, Path::new(KEYS).join(user))?;
        }
    }
    Ok(())
}

fn serve(
    stopping: &AtomicBool,
    owned: &mut BTreeSet<String>,
    daemon: &mut Option<Child>,
) -> io::Result<()> {
    fs::create_dir_all(KEYS)?;
    fs::create_dir_all("/run/sshd")?;
    // /run is pod-local. Stale authorized keys must not survive a restart.
    for entry in fs::read_dir(KEYS)? {
        fs::remove_file(entry?.path())?;
    }
    let mut previous = read_inventory()?;
    sync(&Inventory::new(), &previous, owned)?;
    command("/usr/sbin/sshd", &["-t", "-f", CONFIG], &[0])?;
    *daemon = Some(
        Command::new("/usr/sbin/sshd")
            .args(["-D", "-e", "-f", CONFIG])
            .spawn()?,
    );
    let mut next = Instant::now();
    while !stopping.load(Ordering::Relaxed) {
        if daemon.as_mut().unwrap().try_wait()?.is_some() {
            return Err(invalid("SSH daemon exited"));
        }
        if Instant::now() >= next {
            let desired = read_inventory()?;
            sync(&previous, &desired, owned)?;
            previous = desired;
            next = Instant::now() + Duration::from_secs(2);
        }
        thread::sleep(Duration::from_millis(100));
    }
    Ok(())
}

fn run() -> io::Result<()> {
    let stopping = Arc::new(AtomicBool::new(false));
    for signal in [signal_hook::consts::SIGTERM, signal_hook::consts::SIGINT] {
        signal_hook::flag::register(signal, Arc::clone(&stopping))?;
    }
    let mut owned = BTreeSet::new();
    let mut daemon = None;
    let result = serve(&stopping, &mut owned, &mut daemon);
    // Fail closed on malformed/missing inventory, sync failure, or termination.
    // Attempt cleanup for every account, even if one operation fails.
    if let Some(child) = daemon.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    let mut cleanup = Ok(());
    for user in &owned {
        if let Err(error) = revoke(user) {
            cleanup = Err(error);
        }
    }
    result.and(cleanup)
}

fn main() {
    if run().is_err() {
        eprintln!("ssh-relay stopped: configuration, account sync, or SSH daemon failure");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn row(id: &str, byte: u8) -> serde_json::Value {
        let mut blob = b"\0\0\0\x0bssh-ed25519\0\0\0\x20".to_vec();
        blob.extend([byte; 32]);
        serde_json::json!({"instance_id": id, "public_key": format!("ssh-ed25519 {}", STANDARD.encode(blob))})
    }
    const A: &str = "12345678-1234-1234-1234-123456789abc";
    #[test]
    fn accepts_scoped_account_and_empty_revocation_list() {
        let parsed =
            inventory(serde_json::to_string(&vec![row(A, 1)]).unwrap().as_bytes()).unwrap();
        assert!(parsed.contains_key("ni_123456781234123412341234"));
        assert!(inventory(b"[]").unwrap().is_empty());
    }
    #[test]
    fn rejects_duplicate_keys_and_truncated_account_collisions() {
        let b = "12345678-1234-1234-1234-123456789def";
        for rows in [
            vec![row(A, 1), row(A, 1)],
            vec![row(A, 1), row(b, 2)],
            vec![row(A, 1), row("22345678-1234-1234-1234-123456789abc", 1)],
        ] {
            assert!(inventory(serde_json::to_string(&rows).unwrap().as_bytes()).is_err());
        }
    }
    #[test]
    fn rejects_invalid_input_and_key_options() {
        for raw in [b"null".as_slice(), b"{}", b"[{}]", b"["] {
            assert!(inventory(raw).is_err());
        }
        let mut value = row(A, 1);
        value["public_key"] =
            format!("command=evil {}", value["public_key"].as_str().unwrap()).into();
        assert!(inventory(serde_json::to_string(&vec![value]).unwrap().as_bytes()).is_err());
        let mut value = row(A, 1);
        value["extra"] = true.into();
        assert!(inventory(serde_json::to_string(&vec![value]).unwrap().as_bytes()).is_err());
    }
}
