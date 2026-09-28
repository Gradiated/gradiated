import { sign } from "node:crypto";

import type { KMSClient } from "@aws-sdk/client-kms";

import type { CertificateSigner } from "./certificates.js";

// Made with `openssl req -utf8`, which encodes names as UTF8String like the
// production CA, so an issuer that is re-encoded rather than copied shows up.
export const testCa = {
  certificate: `-----BEGIN CERTIFICATE-----
MIIBhzCCAS2gAwIBAgIUQGGzFMccTr4736JAO1Vu5HPEfkYwCgYIKoZIzj0EAwIw
GDEWMBQGA1UEAwwNVGVzdCBOb21hZCBDQTAgFw0yNjA5MjMyMTExMDRaGA8yMTI2
MDgzMDIxMTEwNFowGDEWMBQGA1UEAwwNVGVzdCBOb21hZCBDQTBZMBMGByqGSM49
AgEGCCqGSM49AwEHA0IABATWSu5SnmT35HWwlaREhxN7XlVMZzIQdPgItC1sBucp
PUzf/fWQazg3IYjQS4JDSLSsQG//1TVJ2J0mTTEEOyijUzBRMB0GA1UdDgQWBBTe
xS6uh0eiZU+gixSgWHUuJwQfuzAfBgNVHSMEGDAWgBTexS6uh0eiZU+gixSgWHUu
JwQfuzAPBgNVHRMBAf8EBTADAQH/MAoGCCqGSM49BAMCA0gAMEUCIEMOyUILMXm/
mAEK/TQmuJYD1YOHlKTd6Bqgpyav9hvlAiEAuRO1FVEagaa+1I2LCBZjmaUvlCAz
zMmx36G18ZK2V+w=
-----END CERTIFICATE-----`,
  privateKey: `-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg9TUfYllbQtT+Y8un
bLOTeCcrUi17FqK7A+0BMEVEPy+hRANCAAQE1kruUp5k9+R1sJWkRIcTe15VTGcy
EHT4CLQtbAbnKT1M3/31kGs4NyGI0EuCQ0i0rEBv/9U1SdidJk0xBDso
-----END PRIVATE KEY-----`,
};

export const localSigner: CertificateSigner = async (message) =>
  sign("sha256", message, { key: testCa.privateKey, dsaEncoding: "der" });

export const fakeKms = () => {
  const requests: {
    KeyId?: string;
    MessageType?: string;
    SigningAlgorithm?: string;
  }[] = [];
  const client = {
    send: async (command: {
      input: {
        KeyId?: string;
        Message?: Uint8Array;
        MessageType?: string;
        SigningAlgorithm?: string;
      };
    }) => {
      const { Message, ...request } = command.input;
      requests.push(request);

      return { Signature: await localSigner(Message!) };
    },
  } as unknown as KMSClient;

  return { client, requests };
};
