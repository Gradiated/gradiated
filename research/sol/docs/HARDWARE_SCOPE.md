# Hardware model scope

The hardware specification covers the path from tensor operation to deployed server economics.

## Device

- Process node, die area, usable yield, reticle and chiplet boundaries.
- Clock domains and thermal design power.
- Compute arrays, vector units, supported numeric formats, accumulator formats, and conversion units.
- Register files, local scratchpads, shared SRAM, banking, ports, capacity, latency, bandwidth, leakage, and access energy.
- HBM or DRAM stacks, channels, capacity, latency, bandwidth, and transfer energy.
- On-die network topology, links, routers, contention, latency, and energy.
- Scale-up and scale-out links, collectives, NICs, and topology.

## System

- Package, memory, board, host, NIC, storage, rack, power delivery, cooling, and spare capacity.
- Idle, active, and transfer power states.
- Deployment lifetime, utilization, availability, and failure reserve.

## Manufacturing economics

- Wafer, mask, IP, EDA, design, verification, prototype, packaging, test, and expected respin cost.
- Yield and known-good-die assumptions.
- Program NRE amortized over useful SLO-compliant tokens.

The simulator reports component-level action counts and bottlenecks. Aggregate FLOPS, bandwidth, hourly cost, and TDP are derived views used only by the analytical screening level.

