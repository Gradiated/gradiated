# KV260 power telemetry

On 15 November 2026 we checked the sensor exposed by our physical KV260 revB. The INA260 at I²C address `0x40` monitors the **5 V VCC_SOM supply**. The starter kit takes 12 V at its input, and the carrier supplies some rails separately. Use this sensor to measure energy supplied through VCC_SOM. A whole-board result needs a separate measurement at the board input, with any other power paths accounted for. [AMD KV260 power specifications](https://docs.amd.com/r/en-US/ds986-kv260-starter-kit/Power-and-Electrical)

Linux exposed the same INA260 as `iio:device1` and as `hwmon2` (`ina260_u14`). The device tree mapped all three hwmon channels to the IIO device. Both interfaces were readable by the ordinary board user. These numbers check the conversion between interfaces. One set of sequential readings cannot establish calibration, idle power or inference energy. [TI INA260 datasheet, §8.5.1](https://www.ti.com/lit/ds/symlink/ina260.pdf#page=17), [Linux IIO units](https://docs.kernel.org/6.1/admin-guide/abi-testing.html#:~:text=Units%20after%20application%20of%20scale%20and%20offset%20are%20milliwatts), [Linux hwmon units](https://docs.kernel.org/hwmon/sysfs-interface.html#power)

| Channel | Direct IIO reading | hwmon reading |
| --- | --- | --- |
| Current | `532 × 1.25 mA = 665 mA` | `665 mA` |
| Voltage | `4045 × 1.25 mV = 5056.25 mV` | `5056 mV` |
| Power | `336 × 10 mW = 3.36 W` | `3,360,000 µW = 3.36 W` |

The installed image and module package were version `6.8.0-1015.16`. The installed module and loaded module reported matching source versions. The driver reported a conversion time of 1.1 ms each for current and voltage and an averaging ratio of four. That gives a nominal period of 8.8 ms per averaged reading, which the driver rounds to 114 Hz. These are settings reported by the driver. The age of a reading when Linux returns it still needs checking. [Ubuntu source package](https://launchpad.net/ubuntu/+source/linux-xilinx/6.8.0-1015.16), [TI INA260 datasheet, §8.4.1](https://www.ti.com/lit/ds/symlink/ina260.pdf#page=16)

## Idle logger check

The unprivileged logger delivered all 200 scheduled reads in one ten-second idle window. The median interval was 50.000 ms and the longest was 50.121 ms. The median read took 0.392 ms and the 95th percentile took 0.498 ms. The process used 42.5 ms of CPU time. This checks Linux read cadence at idle. The CPU figure only covers the logger process, and the read timestamps give no direct measure of ADC sample age. Use a timed load transition or an independent meter to check the sensor response under changing load.

## Proposed inference energy test

1. Reuse a warmed resident session with the [verified speed workload](../experiments/kv260-conditioned-resident-speed-v1.md). Keep the three prompts, weights, arithmetic, 50 MHz configuration, output checks, cooling and peripherals fixed. Use a 12-request block with four requests per prompt. Alternate matched blocks with the sampler off and on across three pairs. Keep the exact output checks enabled and compare admission-to-first-byte latency, verified completion latency and throughput to judge whether logging changes performance.
2. With the sampler on, bracket each active block with matched idle windows. Keep the candidate weights resident and clear the context before each idle window. Allow settling and place the clear outside the active window. Read the direct IIO power channel at 20 Hz with read start, end and request markers on the same monotonic clock. Take samples on both sides of each active boundary. Set the maximum gap and settling rule before collecting data. Keep JSON serialisation and UART export outside the measured phases.
3. Integrate watts from first admission to last verified finish, including capture and verification. Report gross VCC_SOM joules per verified completion and per output byte token. Report the matched-idle subtraction separately. Check sensitivity to time alignment and gaps, and leave small differences unresolved if drift or instrument uncertainty could explain them. The sensor reports in 10 mW steps. Its accuracy also depends on the instrument and measurement conditions.

A logging DC meter at the 12 V input would give whole-board energy for the comparison chart if any other supply paths, including USB power if present, are accounted for.

The Mac captures are under `.agents/runtime/hardware/inference/outputs/` in `kv260-power-inventory-20261115/` and `kv260-power-idle-logger-20261115/`. The manifests pin raw readings, exact commands, UART frames and verification receipts. The inventory also pins the Canonical driver sources. Both checks ran without a model workload or changes to board settings.

| Evidence folder | Manifest SHA-256 |
| --- | --- |
| `kv260-power-inventory-20261115/` | `a2982ea63593d91c81d9602a52ec8f647ec31c9db6c0d9f1332b85a538ed219c` |
| `kv260-power-idle-logger-20261115/` | `f4fc2678546f15122ff924e137ef9fa7e63de24a633891eabd5dc289539a1509` |

## Completed logger comparison

Three same-boot pairs covered 72 measured requests and 36 warm-up requests. All 21 timing comparisons fell within the predefined 2% screen, with a largest absolute change of 0.49%. The logged blocks yielded 2.31–2.32 J per verified completion through VCC_SOM, or 21.9–22.0 mJ per emitted byte. These are block averages and timing observations for this workload. [Findings](../results/power-paired-20261115T155436Z-fd5f12/findings.md) · [Independent audit](../results/power-paired-20261115T155436Z-fd5f12/audit-manifest.json)
