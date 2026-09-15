// Create first-install credentials locally. Never print secret contents.
import { randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

process.umask(0o077);
const directory = process.argv[2];
if (!directory || !path.isAbsolute(directory) || existsSync(directory)) {
  throw new Error("Provide a new absolute directory outside version control");
}
mkdirSync(directory, { recursive: true, mode: 0o700 });
const file = (name) => path.join(directory, name);
const run = (program, args) =>
  execFileSync(program, args, { stdio: "pipe", timeout: 30_000 });
const openssl = (...args) => run("openssl", args);
const read = (name) => readFileSync(file(name), "utf8");
const json = (name, value) =>
  writeFileSync(file(name), JSON.stringify(value), { mode: 0o600 });
openssl(
  "genpkey",
  "-algorithm",
  "EC",
  "-pkeyopt",
  "ec_paramgen_curve:P-256",
  "-out",
  file("ca-key.pem"),
);
openssl(
  "req",
  "-new",
  "-x509",
  "-key",
  file("ca-key.pem"),
  "-out",
  file("ca.pem"),
  "-days",
  "3650",
  "-subj",
  "/CN=Gradiated Nomad CA",
  "-addext",
  "basicConstraints=critical,CA:TRUE",
  "-addext",
  "keyUsage=critical,keyCertSign,cRLSign",
);
const issue = (name, cn, sans) => {
  openssl(
    "genpkey",
    "-algorithm",
    "EC",
    "-pkeyopt",
    "ec_paramgen_curve:P-256",
    "-out",
    file(`${name}-key.pem`),
  );
  openssl(
    "req",
    "-new",
    "-key",
    file(`${name}-key.pem`),
    "-out",
    file(`${name}.csr`),
    "-subj",
    `/CN=${cn}`,
  );
  writeFileSync(
    file(`${name}.ext`),
    `basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth,clientAuth\nsubjectAltName=${sans.join(",")}\n`,
  );
  openssl(
    "x509",
    "-req",
    "-in",
    file(`${name}.csr`),
    "-CA",
    file("ca.pem"),
    "-CAkey",
    file("ca-key.pem"),
    "-set_serial",
    `0x${randomBytes(16).toString("hex")}`,
    "-days",
    "90",
    "-extfile",
    file(`${name}.ext`),
    "-out",
    file(`${name}.pem`),
  );
  openssl(
    "verify",
    "-CAfile",
    file("ca.pem"),
    "-verify_hostname",
    cn,
    file(`${name}.pem`),
  );
};
const servers = { "ca.pem": read("ca.pem") };
for (let ordinal = 0; ordinal < 3; ordinal++) {
  const name = `nomad-${ordinal}`;
  issue(name, "server.global.nomad", [
    "DNS:server.global.nomad",
    `DNS:${name}.nomad-headless.nomad.svc.cluster.local`,
    "DNS:nomad-api.nomad.svc.cluster.local",
    "DNS:localhost",
    "IP:127.0.0.1",
    `DNS:${name}.rpc.gradiated.com`,
  ]);
  servers[`${name}.pem`] = read(`${name}.pem`);
  servers[`${name}-key.pem`] = read(`${name}-key.pem`);
}
issue("operator", "cli.global.nomad", ["DNS:cli.global.nomad"]);
json("ca.json", { "ca.pem": read("ca.pem"), "ca-key.pem": read("ca-key.pem") });
json("server-tls.json", servers);
json("operator.json", {
  "ca.pem": read("ca.pem"),
  "cert.pem": read("operator.pem"),
  "key.pem": read("operator-key.pem"),
});
json("gossip.json", {
  "gossip.json": JSON.stringify({
    server: { encrypt: randomBytes(32).toString("base64") },
  }),
});
console.log(
  "Created bootstrap secret files. CA: 10 years; leaf certificates: 90 days. No values printed.",
);
