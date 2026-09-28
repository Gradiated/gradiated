import { createServer } from "node:https";
import type { AddressInfo } from "node:net";

import { afterEach, describe, expect, it } from "vitest";

import { createNomadGet } from "../src/nomad-allocations.js";

// Test-only self-signed certificate for server.global.nomad.
const cert = `-----BEGIN CERTIFICATE-----
MIIBszCCAVmgAwIBAgIUWExnZ8l8ParSwdmjXgu5YeCTuIUwCgYIKoZIzj0EAwIw
HjEcMBoGA1UEAwwTc2VydmVyLmdsb2JhbC5ub21hZDAgFw0yNjA5MjgxMDEwMDFa
GA8yMTI2MDkwNDEwMTAwMVowHjEcMBoGA1UEAwwTc2VydmVyLmdsb2JhbC5ub21h
ZDBZMBMGByqGSM49AgEGCCqGSM49AwEHA0IABMLRbO75zGPxoiz07AZ+qB/LujHQ
UGrQ7zjhk6O9DikN1TrATUIIMk+u+IFiGttoS5BFllRueqPzpJgIuliQx3SjczBx
MB0GA1UdDgQWBBQo7MRdGIdVELcJaEBoNgTG1oSjhjAfBgNVHSMEGDAWgBQo7MRd
GIdVELcJaEBoNgTG1oSjhjAPBgNVHRMBAf8EBTADAQH/MB4GA1UdEQQXMBWCE3Nl
cnZlci5nbG9iYWwubm9tYWQwCgYIKoZIzj0EAwIDSAAwRQIhAPc49HJUBuEUo7/g
Kqz+RuZknkgQf/s7/W5E5T1EEDPqAiBWayicK9AlsnNx7I9XjYdr4cNCl4onGSjs
Lk5aN05o/w==
-----END CERTIFICATE-----`;
const key = `-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgPIpSE/DWOWQJtVvJ
/C7DCk+ps0WX5fvYOzC/WUV1ma2hRANCAATC0Wzu+cxj8aIs9OwGfqgfy7ox0FBq
0O844ZOjvQ4pDdU6wE1CCDJPrviBYhrbaEuQRZZUbnqj86SYCLpYkMd0
-----END PRIVATE KEY-----`;

let close = () => {};
afterEach(() => close());

const nomadResponding = async (respond: Parameters<typeof createServer>[1]) => {
  const server = createServer({ key, cert }, respond).listen(0);
  await new Promise((resolve) => server.once("listening", resolve));
  close = () => {
    server.closeAllConnections();
    server.close();
  };

  return createNomadGet({
    NOMAD_ADDR: `https://127.0.0.1:${(server.address() as AddressInfo).port}`,
    NOMAD_TOKEN: "token",
    NOMAD_CA_PEM: cert,
    NOMAD_CLIENT_CERT_PEM: cert,
    NOMAD_CLIENT_KEY_PEM: key,
  });
};

describe("Nomad HTTP client", () => {
  it("rejects with the status code when Nomad refuses", async () => {
    const get = await nomadResponding((_, response) => {
      response.writeHead(403);
      response.end("denied");
    });

    await expect(get("/v1/jobs")).rejects.toMatchObject({ code: "403" });
  });

  it("rejects instead of hanging when the connection resets mid-response", async () => {
    const get = await nomadResponding((request, response) => {
      response.writeHead(200);
      response.write("[{");
      setTimeout(() => request.socket.destroy(), 50);
    });

    await expect(get("/v1/jobs")).rejects.toMatchObject({ code: "ECONNRESET" });
  });
});
