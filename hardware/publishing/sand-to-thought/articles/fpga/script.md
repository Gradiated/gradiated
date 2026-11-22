# Inside our FPGA

A chip you can reconfigure.

<!-- scene: reconfigure -->

## A chip that can change its job

A field-programmable gate array, or FPGA, is a chip whose internal circuit we can configure after manufacture. Think of it as blank slate of of available logic blocks and wires arranged in a grid which we can connect in almost any way we'd like.[@fpga-introduction] The transistors and metal wires already exist, but logic outputs and signal pathways can be written into small SRAM memory blocks spread throughout the chip.

In this article we will demonstrate the basic workings of an FPGA along with all its advantages, such as configurability (they are **P**rogrammable in the **F**ield), speed, parallelisability and ability to simultaneously read and control huge numbers of inputs and outputs. Its disadvantages include high cost and power consumption, and complexity. Later we will use our FPGA (AMD's KRIA KV260) to run inference of a tiny LLM, and explore ways of improving performance.

<!-- scene: map-io -->

Around the edge of the chip, input/output blocks connect the internal circuit to physical pins and thus the outside world. Pins can be configured to receive signals, send them, or do both. Other dedicated pins such as the power supply are not shown.[@ice-forty]

This large number of connections lets an FPGA exchange several streams of data at once. This is useful anywhere needing lots of fast data movement: cameras, large displays, robots and drones. However the achievable data rate depends also on the user's custom design implemented within the FPGA's circuits, not simply the number of pins.[@sensor-processing; @led-video-display; @drone-processing]

<!-- scene: map-logic -->

The larger squares are configurable logic blocks, or CLBs. Each contains circuitry with stored settings that we can choose, dictating how it transforms its incoming signals into outputs. Later, we will open one up and see how it stores and performs a simple task.[@clb-overview]

<!-- scene: map-routing -->

The CLBs and I/Os are interconnected by many wires carrying electrical signals.[@ice-forty]

<!-- scene: map-junctions -->

The routes these wires take is chosen by electrically controlled, configurable switches. Stored settings at the wire junctions choose which wire segments they connect, directing signals through the chip.[@ice-forty]

<!-- scene: first-circuit -->

Let’s configure our first circuit. We can represent one bit, either `0` or `1`, using a low or high voltage respectively. A logic gate is a circuit that takes one or several inputs and produces an output bit according to a set rule.

We choose two pins as inputs, `A` and `B`, and one as an output. Our selected paths lead through the upper-left CLB, which we have configured to perform the logic gate AND: its output is `1` only when both inputs are `1`. With `A = 1` and `B = 1`, the output is `1`.

<!-- scene: input-change -->

Say `B` now changes to `0`. The inputs are no longer both `1`, so the output becomes `0`. The AND rule and connections stay in place: the circuit responds to a new input without being reconfigured.

<!-- scene: rule-change -->

Now keep `A` at `1` and `B` at `0`, and change the stored rule in the CLB to OR. OR outputs `1` if at least one input is `1`, so our output changes to `1`. The same block and paths perform a different function because we changed a setting inside the CLB.[@fpga-introduction]

Changing an input supplies new data. Changing the stored rule reconfigures how that data is processed. Before peering inside a CLB to explore how they work, let’s consider why engineers use FPGAs at all.

<!-- scene: why-fpgas -->

## Why use an FPGA?

Imagine our chip among the electronics of a particle detector at CERN. Particles produced in a collision scatter and pass through layers of sensors, which produce electrical signals for the processing electronics.[@detector-signals] There is far too much data to record in full, with collision rates reaching billions per second.[@atlas-data-acquisition]

In the first stage of filtering, FPGAs check signals from several parts of the detector as the data arrives.[@cern-fpga-trigger] The system passes on events that meet the experiment’s selection criteria for closer analysis.[@atlas-trigger] It discards the rest, leaving much less data to process and store.[@atlas-data-acquisition]

<!-- scene: why-display -->

Now imagine the same chip sits between incoming live video and a set of large LED displays, perhaps at a live concert. Each display tile needs the correct pixels at the correct time, with as little delay as possible. The FPGA organises the picture and sends several streams of pixels to the LED display circuits in parallel.[@led-video-display]

This case requires a large amount of both input and output data processing each second, and very meticulous and coordinated timing. A good FPGA design can do all of this at once.

<!-- scene: why-prototype -->

And for perhaps our most relevant use case: testing a circuit we might eventually manufacture as an application-specific integrated circuit, or ASIC: a chip designed to accelerate a particular tast, but unalterable once mass-produced. Engineers can load a proposed design, supply test inputs, read the results and reconfigure the FPGA to correct mistakes before making the final custom chip.[@fpga-prototyping] The prototype tests behaviour rather than the final ASIC’s speed or power consumption.

These examples show the advantages we introduced at the start. At CERN, an FPGA processes many inputs in parallel to make fast decisions. For the display, it coordinates many outputs with precise timing. In the prototype, reconfigurability lets engineers correct and test a design without manufacturing another chip.

The trade-offs matter too: our design must fit the chip’s available resources, and making it work can be complex. We’ll also consider cost and power consumption, which often make other chips a better choice for most tasks. First, let’s return to the chip and open one logic block to understand how these capabilities work.

<!-- scene: inside-chip -->

## Inside a logic block

Let's zoom in on one configurable logic block.

<!-- scene: clb-resources -->

A CLB contains several look-up tables, or *LUTs*: small circuits that store an output for each possible combination of inputs. It also contains *flip-flops*, which remember results. We’ll examine each in turn. CLBs in our FPGA contain eight LUTs and sixteen flip-flops, alongside other circuitry.[@clb-overview]

<!-- scene: inside-clb -->

We will follow one LUT and one flip-flop. We’ll start with how the LUT produces a result in a small corner of the FPGA chip, then see how the flip-flop remembers and moves it.

<!-- scene: truth-table -->

A LUT implements a logical rule by storing the output bit for every possible combination of inputs. Our example has two inputs, `A` and `B`, giving four combinations: `AB = 00`, `01`, `10` and `11`. This means we need four storage bits to decide what the output should be for each of these inputs.

In the figure, the `AB` column labels these input combinations. For each input, there is a stored output answer in SRAM, resulting in four bits of SRAM. The input signals `A = 1` and `B = 0`, select the SRAM answer bit for `10`. For AND, shown in the figure now, that answer is `0`: only `11` gives `1`. Changing the stored answers in SRAM changes the logic rule. OR, for example, gives `1` whenever either input is `1`:

| `A` | `B` | Stored SRAM for AND | Stored SRAM for OR |
| --- | --- | --------------------- | -------------------- |
| `0` | `0` | `0`                   | `0`                  |
| `0` | `1` | `0`                   | `1`                  |
| `1` | `0` | `0`                   | `1`                  |
| `1` | `1` | `1`                   | `1`                  |

<!-- scene: selector -->

Selection circuits called [multiplexers](/library/sand-to-thought/how-to-get-an-answer-out-of-sand/#sand-select-values), labelled MUX, connect one of those answers to the output. A two-input MUX uses a selection bit to choose its first input for `0` or its second for `1`.[@multiplexers]

Here, the input `B` is connected to the first two MUXes, and selects within each pair of answers. `A` is connected to the final MUX and selects between the pairs. With `A = 0` and `B = 1`, the final MUX selects the top channel and the top MUX selects its lower input, resulting in a final output with the answer from SRAM row `01`, which is `0`, as expected for AND. The input signals are designed to select a path through the circuit. They do not search the rows one after another or rewrite the stored answers.[@nandland-luts]

Let’s make the same change we saw at the start, from AND to OR, by rewriting those two bits.

<!-- scene: stored-bit -->

## Writing the stored rule

Let's zoom into the SRAM block for row `01`. Static random-access memory, or SRAM, uses the feedback principle we explored in [Sand to Thought’s Memory chapter](/library/sand-to-thought/how-to-get-an-answer-out-of-sand/#sand-latch). In this case, two connected NOT gates reinforce opposite values (while power is supplied).[@sram-writing]

The triangles with small circles at their tips represent NOT gates, each [built from two transistors](/library/sand-to-thought/fabricating-a-transistor/#fab-destination). The two dots on the wires show where each NOT gate’s output connects to the other’s input. The right side of the cell holds the LUT’s stored answer. The left side of the cell holds the opposite value. The two access transistors act as switches that connect each side of the cell to its writing wire.

With access set to `0`, the switches are off and the cell holds `0`, even though the writing wires are ready to change it.

<!-- scene: write-and-hold -->

To store a `1`, we set the left writing wire to `0` and the right one to `1`. Turning access on connects the writing wires to the cell. The left side of the cell goes low. The right side of the cell goes high, changing the stored answer to `1`.[@sram-writing]

<details>
<summary>Don't we get a short circuit?</summary>

Yes, briefly. The yellow dots show current flowing from the power supply to ground (0 V). The animation below repeats that brief moment.

<figure class="fpga-inline-circuit">
<img src="/assets/fpga/sram-write-contention.svg" width="524" height="366" alt="Six-transistor SRAM cell. Moving yellow dots trace one temporary current path from the supply through a pull-up and an access transistor to a writing wire held at ground by the external writing circuitry.">
</figure>

The writing circuit pulls the left side of the cell low. The right side goes high, switching off the transistor at the top left. That cuts off the current shown by the dots.[@sram-writing]

</details>

<!-- scene: cell-hold -->

Turn access off again. The writing wires are isolated from the storage circuit, and powered feedback maintains the new answer. We have successfully programmed this storage cell from a `0` to a `1`.

<details>
<summary>Why use SRAM?</summary>

SRAM-style storage provides compact, rewritable memory bits using only six transistors, whose voltages remain available while power is supplied. Unlike dynamic RAM (DRAM), it does not need periodic refreshing, however it does also lose its contents when power is removed.[@memory-technologies]

</details>

<!-- scene: lut -->

Now zoom back out to the complete LUT. We changed row `AB = 01` from `0` to `1`. Repeating that write for row `10` completes the change from AND’s `0, 0, 0, 1` to OR’s `0, 1, 1, 1`. The selector circuit formed of MUXes stays the same, all that needs to change are the SRAM answer bits.[@fpga-introduction] We have rewritten the answers to convert this LUT into an OR gate.

For a single output, `n` input LUT we need `2ⁿ` SRAM answers: four inputs need `2⁴ = 16`, while six need `2⁶ = 64`. Several LUTs can be stacked together to perform more complex functions.[@nandland-luts] A larger LUT can reduce the number of logic stages and wired connections, but each extra input doubles its answer storage and requires more MUXes. Manufacturers balance these costs against speed.[@lut-size-tradeoff]

We will return to how this SRAM configuration data reaches the chip later.[@configuration-frames]

<!-- scene: flip-flop -->

## Keeping a result

Let's zoom back out to our CLB. After the LUT comes a flip-flop: a circuit whose output remembers one bit. It is designed to hold, at its output, the last bit value fed into its input, when the clock was last triggered. Between clock triggers, it holds that saved value even if the input changes, which allows the LUT's previous result to be held steady and passed into later LUTs/CLBs for processing while the preceding LUT calculates the next value. Here, the LUT has prepared `1`, but the flip-flop still holds `0` from an earlier capture.[@nandland-flip-flops]

For a closer look inside a flip-flop, see MIT’s illustrated explanation.[@flip-flop-latches]

<!-- scene: logic-block -->

Now the clock is triggered, and the flip-flop captures the waiting `1` from the LUT. The bit's signal moves from the input side to the output side, and the saved value becomes `1`. Each later clock pulse captures the input again. Between pulses, the saved output stays in place.

<!-- scene: flip-flop-hold -->

Now let's pause the clock and change the LUT’s inputs, forcing its output become `0`. With no new trigger, the flip-flop’s saved value stays `1`.

The MUX on the right chooses what leaves the logic block. It can send the LUT’s new `0` straight through to be immediately processed or pass on the `1` the flip-flop has buffered from the last clock pulse.

<!-- scene: clb-output-setting -->

A bit stored in SRAM tells the MUX which path to use.[@clb-overview] Here the setting is `1`, so the MUX selects the flip-flop and the block sends out the saved `1`.

The LUT’s SRAM configuration remembers the logic or function the LUT should enact, while the flip-flop's memory remembers and buffers a result produced as the circuit runs. We will introduce more kinds of memory and their uses in our FPGA later.

<!-- scene: routing-grid -->

## Choosing the connections

Now we zoom back out to see the whole chip. While one CLB can only perform simple calculations among its array of LUTs and flip-flops, combining blocks introduces the possibility to perform much larger, more complex maths and functions. This programmable routing is achieved using the wires and configurable switches between CLBs.[@ice-forty]

Let's zoom into one particular switch at the junction between four CLBs. This switch is connected to, at its inputs, a wire from the upper-left CLB `1` and the one below it (`4`). Its output feeds into the central CLB `5`.[@routing-interconnect]

<!-- scene: routing-switch -->

Inside, another MUX connects one of two incoming wires to an outgoing wire.[@multiplexers] A configuration SRAM cell holds a bit whose voltage controls the MUX's transistors. With its SRAM set to `0`, the CLB `1` is connected to CLB `5`, carrying signal `1`. The lower wire remains unselected.[@fpga-introduction; @configuration-physical]

This is another important use of SRAM configuration memory: here it remembers a connection choice rather than a LUT answer. This setting stays in place while data signals pass through, and the MUX behaves as a railway switch for voltage. Each junction contains many MUXes and configuration bits, giving us much freedom in the connections between CLBs.

<!-- scene: routing-change -->

Rewrite the SRAM setting to `1`. Now, CLB `4` is connected to CLB `5`, carrying signal `0`. The transistors inside the MUX now select a different existing path - the wires themselves have not moved.

Each of these switches take up space. Compared with a hardwired chip wired for the same job, signals may travel along longer wires or through more switches. Charging and discharging those longer wires and extra connections can use more energy and take more time, but this is the trade-off for configurability.[@fpga-asic]

<!-- scene: configuration-map -->

We changed one connection by rewriting a single bit. How do we load all the SRAM settings for a whole circuit?

<!-- scene: configuration-source -->

## Configuring the whole chip

Let’s widen the circuit to allow more blocks on our chip. To configure our FPGA, we need to load a file of settings called a *bitstream*, which can be stored in off-chip flash memory.[@flash-memory] This file contains data of all the bits we should set each of our SRAM cells to. We do this by introducing the *configuration block* on the chip which receives these settings and sends out that information into the SRAM spread throughout the logic and routing.[@configuration-physical]

Before we can load a bitstream, design tools have to fit our circuit into the available blocks, find routes between them and check that signals arrive in time for the next clock edge. A design can give the right answers in simulation and still miss its timing target. An early version of our inference circuit missed its target of `100 MHz`, or 100 million clock cycles per second.

<!-- scene: configuration-distribute -->

First, the configuration block writes a red `0` into the routing MUX’s SRAM cell, using a separate loading connection. This selects the upper incoming wire connecting CLB `1` to CLB `5`.[@configuration-load]

<!-- scene: configuration-luts -->

Looking inside CLB 1 we see four simplified LUTs, each with four SRAM answer bits. Our configuration block sends data to each, setting each LUT to respectively perform AND, OR, NOR (NOT OR) and NAND (NOT AND) operations. In reality this writing occurs in batches.[@configuration-frames]

<!-- scene: clock-network -->

All the many flip-flops inside CLBs also need a shared clock to coordinate when to move results across to their next position. Let's add a clock system to distribute an incoming clock through a dedicated network of wires and buffers, separate from ordinary data routing. This delivers the oscillating clock signal across the chip with minimal difference in arrival times.[@clock-network]

<!-- scene: resources-map -->

## Memory and arithmetic

So far, we have used SRAM to hold settings, and flip-flops to hold results. But suppose our circuit receives a stream of, say, sensor readings and needs to keep many of them for later. We need somewhere to store a collection of numbers.

LUTs can hold information in its SRAM instead of a logic rule. This use is called *distributed RAM*.[@distributed-ram] It is useful for small memories, but storing larger collections this way can use up the CLBs we need for calculations and control.[@distributed-ram-use]

To fix this problem let's introduce a dedicated tool for data storage: *block RAM*, or BRAM. Its data is organised into groups of bits called *words*, each with an address identifying its location. We could save one word at address `0`, the next at `1` and so on, to read them back when needed, much like the memory array we built in [Sand to Thought’s Memory chapter](/library/sand-to-thought/how-to-get-an-answer-out-of-sand/#sand-memory-array).[@fpga-architecture]

<!-- scene: block-ram -->

Let’s zoom into that memory block. Like the LUT storage, BRAM uses SRAM cells. Here we will store information for the circuit to work on, rather than the answers that define a LUT’s logic rule. Saving a new reading changes the data at the chosen address.

Our KV260’s FPGA has 144 BRAM blocks, together providing about 660 kilobytes (KB) of storage. Its LUTs can also provide up to roughly 450 KB of distributed RAM.[@our-memory-capacity]

Our FPGA also has 64 larger dedicated SRAM blocks called *UltraRAM*, providing another 2.4 megabytes (MB) of storage.[@our-memory-capacity] Each holds eight times as much as a BRAM block and can be linked to others to store larger collections of data, such as model weights, without using LUTs for storage.[@ultraram]

Our example figure stores four `4-bit` words. The thick lines with slashes represent bundles of wires, called *buses*. The address bus has two wires, each carrying one bit. Together they carry the signals `00`, `01`, `10` or `11`, selecting locations `0`, `1`, `2` or `3`. Each data bus (read or write) has four wires, one for each bit of the word, such as `0011` for the number `3`. To read, the circuit supplies an address and receives the stored word. To write, it supplies an address, a new word and a write-enable signal, set to `1` to allow writing or `0` to prevent it. The clock pulse determines when the memory carries out the read or write.[@nandland-block-ram]

In the figure, each square is one SRAM bit, with green `1`s and red `0`s. Our example begins with a BRAM full of SRAM zeros, then automatically writes random words to different addresses. You can pause it and choose your own address and data. Write enable opens the small gate on the data bus (this is a visual aid, not a literal moving part). The selected row saves the new bits when the clock pulse arrives.

The address, data and control wires connect to other blocks through the routing grid, allowing CLBs to control BRAM.[@bram-configuration]

<!-- scene: arithmetic-map -->

We can now store our readings and processed data, but what if we want to perform the common task of multiplication? We could build a multiplier from LUTs and other CLB circuitry, but this can use up many resources.

Adding two unsigned 12-bit numbers takes on the order of 10 LUTs, plus dedicated carry logic.[@adder-lut-estimate] Multiplying them takes on the order of 100 LUTs in AMD’s examples.[@multiplier-lut-utilisation] On our FPGA, the same multiplication fits into one DSP block.[@our-memory-capacity]

A *digital signal processing* block, or DSP block, provides dedicated multiplication and addition circuitry already hardwired into the silicon, leaving more CLBs free for other tasks.[@fpga-architecture] Its specialised circuitry can be faster and use less power than an equivalent circuit built from CLBs.[@dsp-arithmetic]

<!-- scene: arithmetic-blocks -->

Let’s zoom into a DSP block. Here, a stored reading of `3` is multiplied by `2`, producing `6`. The ready-made multiplication circuitry is already there, connected to inputs. We only need to configure how to connect it, rather than constructing the multiplier from LUTs.[@xck26-dsp-type; @dsp48e2-diagram] [See Xilinx’s detailed DSP block diagram.](https://docs.amd.com/api/khub/documents/pTysoma4TYgNH95BrY1Sbw/content#page=8)

<!-- scene: arithmetic-accumulate -->

DSP blocks can also add each new product to a *running total*, the sum of the products processed so far, which turns out to often be very useful.[@dsp-arithmetic] The DSP’s built-in output register holds this total between clock edges. It uses one flip-flop for each bit of the total (we have only shown one), which updates once per clock cycle. The saved register value starts at `0`. The multiplier supplies `6`, and the adder prepares `0 + 6 = 6`. The register still holds `0` until the next clock trigger - scroll down to trigger the clock.

<!-- scene: arithmetic-save -->

Upon a clock trigger, the register replaces `0` with `6`. Its output connects back to the adder along the lower wire which lets the next addition use the running total.

<!-- scene: arithmetic-next -->

Say we have a new set of inputs `2 × 2` producing `4`. The adder combines this with our saved `6`, preparing `6 + 4 = 10`. The next clock trigger replaces the saved total with `10`. We have added two products, `6` and `4`, using the same multiplier, adder and register.

<!-- scene: pins -->

Finally, the I/O blocks around the chip's edge provide another source of input and output data. They receive signals from physical pins and drive signals out through them.[@ice-forty]

In this example, a signal from an input pin starts the calculation. The CLBs tell BRAM which pair of numbers to send to the DSP. The DSP updates the running total, and the result leaves through an output pin.

Our inference design will use DSPs this way, reusing the arithmetic circuitry across many pairs and we will follow how a neural network activation calculation maps on to a DSP soon.

<!-- scene: memory-roles -->

Configuration SRAM memory holds the settings that define the circuit’s logic and connections. Flip-flops keep individual bits, such as those in the DSP’s running total, directly available to the logic that uses them. Some LUTs can store small collections of working data as distributed RAM.[@distributed-ram] BRAM provides a dedicated data bank that packs more bits into the same chip area than a bank of flip-flops. The trade-off is that the circuit can read or write only a few bits per block at a time.[@fpga-architecture]

In our inference design, we use BRAM for the model’s weights and for the KV cache.

<!-- scene: resource-columns -->

Real FPGAs contain many copies of CLB, BRAM and DSP blocks. Different chip families provide different mixes, quantities and memory configuration.[@resource-columns]

Together, these blocks form a simple FPGA: BRAM holds data, DSPs multiply and add, and CLBs implement the remaining logic, save results and control what happens next. Routing carries signals between them, while the clock coordinates when calculations are performed and results are captured. By configuring these blocks of specialised circuits and their connections, we can build our neural-network inference circuit.

<!-- scene: neuron-map -->

## Our FPGA’s first neuron

Our goal is to run a tiny language model on our FPGA. Given some text, it predicts the next piece of text, called a *token*. It then uses that token to help predict the next one.

We trained an extremely small, rather mindless model with 26,720 parameters on forty-eight chip jokes we wrote ourselves. It is heavily overfitted, so it tends to repeat the jokes it has seen. Our tiny model shares the basic architecture of much larger language models. It gives us a way to test, on a small scale, ideas that could make inference faster or more energy-efficient on larger models.

<!-- scene: network-layers -->

The drawing shows how one token passes through our model. It starts as a list of pre-learned numbers. Attention combines information from this token and earlier ones. The next set of results from calculations in the feed-forward network is added to those numbers again, and the model uses the final result to score possible next tokens.

<!-- scene: network-sum -->

Let’s zoom into one of those calculations. Each incoming number is multiplied by a *weight*, a number learned during training. Adding the products gives a weighted sum. This is the arithmetic at the heart of an artificial neuron.[@neural-network-basics]

To make it easy to follow, we show just two inputs, `3` and `2`, with weights of `2` and `−1` for each connection.

<!-- scene: network-products -->

The first connection contributes `3 × 2 = 6`. The second contributes `2 × (−1) = −2`, reducing the total. Together they give `6 + (−2) = 4`. The result becomes one of the numbers used by the next calculation in the next neural network layer. The weights stay fixed throughout.

<!-- scene: neuron-hardware -->

We already have the FPGA blocks needed for this sum. BRAM holds the input numbers and weights. CLBs control which pair to read next, and a DSP multiplies the pair and adds its product to a running total.

The two connections in our network drawing can take turns through the same DSP. We can reuse that circuitry for other neurons too. Let’s open it and follow the same numbers.

<!-- scene: neuron -->

First, memory supplies input `3` and weight `2`. The multiplier produces `6`. Our running total starts at `0`, so the adder prepares `0 + 6 = 6`. A clock edge saves `6` in the DSP’s register, just as in our earlier running-total example.

<!-- scene: neuron-next -->

Next, memory supplies input `2` and weight `−1`. The same multiplier now produces `−2`. The adder combines it with the saved `6`, and the next clock edge saves `4`. We have carried out both connections using one multiplier, one adder and one register.

This is one small part of a neuron’s calculation. Neural networks also apply rules that reshape these sums before passing numbers onward. Our transformer combines many such calculations to produce its next-token scores.

<details>
<summary>What else can a neuron do?</summary>

A simple neuron can add a learned offset, called a *bias*, then apply an output rule. For example, adding a bias of `−1` to our sum of `4` gives `3`. A common rule keeps a non-negative result and replaces a negative one with `0`, so this neuron would output `3`.[@neural-network-basics]

Our transformer uses no added biases and has a different output rule. The multiply-and-add calculation we have just built is shared by both examples.

</details>

<details>
<summary>Can our neural network use fixed-point numbers?</summary>

Fixed-point numbers represent fractions using integers and an agreed scale. If we count in sixteenths, stored `20` means `20 ÷ 16 = 1.25`. Using fewer bits saves memory and can simplify the arithmetic, but rounding can change the model’s predictions.[@inference-quantisation; @fpga-fixed-point]

Each input and weight in our weighted sum fits in 16 bits. A product can need up to 32 bits, and adding many products can take even more room. The DSP keeps the running total in 48 bits. Once it has added all the products, we [rescale and round the result](#fpga-projection) to store it in 16 bits.

</details>

<details>
<summary>What makes addition faster?</summary>

We saw how adding one bit position can produce a carry for the next. A carry chain provides dedicated paths for these carries between neighbouring logic cells, helping an addition finish sooner.[@ice-forty]

</details>

<!-- scene: transformer-cache-map -->

## Running a tiny transformer

The first words of a sentence can change what comes next. Our transformer uses *attention* to decide how much information to draw from each token it has processed so far. Each time it processes a token, it makes a *key* and a *value*, both lists of numbers. The key helps a later token decide how much to draw on this position. The value supplies the numbers it can draw on. The multiply-and-add operation we just followed helps make these lists. Let’s zoom back out from the DSP to see where we keep them.

<!-- scene: transformer-cache -->

Let’s open block RAM. The first two rows of the *KV cache* hold keys and values for tokens we’ve already processed. Each new token adds its own pair. Attention compares the current token’s *query*, another list of numbers, with the stored keys to decide how much of each value to mix in.[@transformer-attention]

To calculate the query, the FPGA starts with the same weighted sum we saw in the neuron example. For each sum, the FPGA reuses one DSP multiplier 32 times, multiplying one input by its learned weight each time. It adds each product to a running total.

Each square represents one number. In a filled grid, green means positive, red means negative and grey means zero. Each key and value has one grid per attention head. We follow the first head. The gold lines show all four values flowing into the mix.

Each token adds `128` bytes to our cache. Saving those numbers lets us reuse them for later predictions. The learned weights stay the same as the cache grows.

<details>
<summary>How are the cache addresses arranged?</summary>

There is room for `256` tokens, including the start token, so the cache can hold `32 KiB`. Each position contributes thirty-two rotated `K` numbers and thirty-two `V` numbers, each sixteen bits wide.

`K` and `V` occupy separate memory banks. In each bank, `word address = position × 32 + coordinate`. Position `255`, coordinate `31`, selects word `8191`. Each word occupies two bytes. The cache preserves the integers exactly. `K` uses scale `2⁻¹¹`, and `V` uses `2⁻¹²`.

In our earlier component simulation, a position becomes readable once all thirty-two pairs have been written. Reset marks every position invalid, so the controller refuses reads even though the old bits remain.

</details>

<!-- scene: token-journey -->

Let’s follow the first two predictions from a request containing the letter `a`. Once the FPGA has processed the prompt, it sends a list of scores to the CPU. The CPU picks the token with the highest score, adds it to the output and sends it back through the model. That pass adds another entry to the cache and produces scores for the next token. The animation uses an edited version of the software reply.

Picking the highest score is a simple job for the CPU. Sending it all 320 scores also lets us compare the FPGA’s results with our software model. The round trip adds time to every prediction as the FPGA waits for the chosen token to come back. In our first experiment, we move that choice onto the FPGA and measure the time saved.

<details>
<summary>How exactly is text encoded and a token chosen?</summary>

Our model splits each byte of the prompt into two input tokens. The letter `a` is one byte, so it becomes two tokens after the start token. On output, each token that contributes to the reply represents one byte.

UTF-8 represents text as bytes. Split each input byte into its high and low hexadecimal digits. For byte `b`, the tokens are `272 + (b >> 4)` and `288 + (b & 15)`. The start token is `256`. For example, `a` is byte `97`, hexadecimal `61`. Its high digit gives `272 + 6 = 278`, and its low digit gives `288 + 1 = 289`. With the start token, that is `[256, 278, 289]`. This encoding is lossless. Inputs longer than forty-eight bytes are rejected, rather than silently cut short.

Output byte tokens are `0` through `255`. The end token is `257`, and the vocabulary has `320` slots in total. The CPU uses *argmax*, choosing the largest of all `320` scores without random sampling. There is no input hash, joke identifier, sentence lookup, retry or output replacement. Each request starts a new completion rather than retaining a chat history.

</details>

<details>
<summary>What is inside our tiny model?</summary>

Normalisation rescales a list of working values before the next learned calculation. It does not change the stored weights. A residual connection adds an earlier list back to a transformed list, preserving a path for those earlier values.

It has one Llama-style transformer block: one attention section and one feed-forward section, with normalisation and residual connections. Its working vectors contain thirty-two numbers, and its two attention heads each use sixteen. SwiGLU makes two `128`-number projections, applies a smooth nonlinear rule to one and multiplies them together, then projects the result back to thirty-two. This differs from our earlier illustrative neuron’s bias and negative-to-zero rule.[@llama-architecture]

We use rotary position embeddings, or RoPE. Treat two coordinates as the components of an arrow, then rotate them by an angle determined by token position. This changes how queries compare with keys at other positions. `Q` and `K` are rotated. `V` is not. It rotates pairs of numbers, not words, and an individual coordinate need not have a recognisable human meaning.[@rotary-position]

Weights, stored activations and cached keys and values use sixteen bits. Dot-product accumulators use forty-eight bits, while scores and some other calculations use wider values. Not every calculation is sixteen-bit. The learned weights occupy `53,440` bytes. We are teaching inference, not winning a text-compression competition.

</details>

<details id="fpga-projection">
<summary>How does one projection use our weighted sum?</summary>

For one output of a projection, take thirty-two input numbers, multiply each by its corresponding learned weight, then add the products. A projection makes a new set of numbers from its input in this way. To produce the next output, use another row of weights with the same inputs.

In the recorded software request for `a`, the first input after normalisation is `1382`, its weight is `1663`, and their product is `2,298,266`. After thirty-two products, the sum is `−100,126,855`. The input scale is `2⁻¹¹` and the weight scale is `2⁻¹⁵`, so products and their sum use `2⁻²⁶`. The stored output uses `2⁻¹¹`. Divide the sum by `2¹⁵ = 32,768` and round to the nearest integer, giving `Q[0] = −3056`. Ties round to the even integer. The same circuit starts a fresh sum with the next row of weights to produce `Q[1] = −1688`.

</details>

<!-- scene: our-board -->

Let’s return to our KV260 and see where its parts sit. A smaller board mounted on it, the K26 module, carries a Zynq UltraScale+ chip. The chip combines Arm CPUs that run software with the [programmable logic](#fpga-reconfigure) we have introduced.[@our-board-system; @our-board-processors] Both are built from the kinds of [logic gates we met in Sand to Thought](/library/sand-to-thought/how-to-get-an-answer-out-of-sand/#sand-not). The larger carrier board provides power and connections to other devices.[@our-board]

- **DDR4 RAM**, on the module, holds running programs and working data for both the CPU and FPGA. It is separate from the FPGA’s block RAM.[@kv260-hardware]
- **Boot flash**, also on the module, retains startup software, called firmware, without power.[@kv260-boot-flash; @flash-memory]
- **microSD** is removable storage on the carrier. In the standard KV260 setup, it holds the Linux operating system and application files.[@kv260-sd-storage]
- **Controllers** handle transfers to and from DDR4, boot flash and microSD.[@our-board-processors; @kv260-interfaces] The FPGA logic can also access DDR4 through the memory controller without asking the CPU to fetch each value.[@kv260-ddr-access]
- **Power in** connects an external supply. Regulators convert its voltage into the supplies needed by the board and module.[@kv260-power]

<!-- scene: board-request -->

In our text-input design, the laptop sends the prompt and displays the returned text. The module reads its firmware from boot flash, then loads Linux from microSD into DDR4 for the CPU to run.[@kv260-boot-flash; @kv260-sd-storage] Before inference, software running on the CPU loads the model’s weights into the FPGA’s BRAM.

The laptop can send the prompt to the CPU through the carrier board’s Ethernet port.[@kv260-ethernet] The CPU sends input tokens to the FPGA. The FPGA logic does the neural-network arithmetic and holds the KV cache in BRAM. It returns a score for each possible next token. The CPU chooses the highest-scoring token and sends it back to the FPGA for the next prediction. It also sends the token’s text to the laptop, where the reply grows one character at a time. 

The CPU–FPGA exchange stays inside the Zynq chip.[@our-board-system] The FPGA reads its weights from BRAM in this build. In [experiment 12](#fpga-measure-lutram), we move some of those weights into LUT memory. In [experiment 14](#fpga-measure-ddr-weight), we start fetching weights from DDR4 during inference.

<!-- scene: measuring-inference -->

## Measuring inference on the KV260

How much faster and cheaper could our FPGA run inference? With help from GPT-6 Astra, we ran iterative experiments to test changes to how the FPGA does its arithmetic, uses memory and shares work with the CPU, measuring how each change affected reply speed and energy use. We started with the circuit we just saw, where the CPU picks the next token. In each experiments below, we tried changes such as reading weights from BRAM sooner or calculating several scores at once. For each board comparison, we ran the starting circuit and the modified circuit on the same KV260. We gave them the same three prompts and always checked that both produced exactly the expected replies.

We kept the model architecture, learned weights and fixed-point number format constant throughout. We kept the FPGA clock at 50 MHz through experiment 23, so the circuit had to fit the same work into fewer ticks to finish sooner. In the last experiment we changed the clock itself.

For each prompt, we measured how long the board took to deliver the first token (*time to first token*, or TTFT), then how quickly the rest of the reply arrived (*decode speed*, in tokens per second) and finally the average energy per output token.

We estimated energy per token from the K26 module’s power readings.[@kv260-power]

<details>
<summary>How did we measure speed and energy use?</summary>

We kept the weights loaded, started each prompt with an empty KV cache and ran one request at a time. The three fixed prompts were `Hello`, a six-byte gibberish prompt and a 48-byte prompt. Each point in the graph combines results from all three prompts. After warming up each circuit, to gather statistics we measured six replies per prompt through experiment 14 and eight from experiment 15 onward. The board’s CPU timed each request from just before prompt preparation. Laptop communication and weight loading fall outside that interval.

For time to first token, we average the wait across the measured replies to all three prompts. For decode speed, we count the output tokens after the first in each reply and divide by the total time from first to last token across those replies.

To estimate energy per token, we added up the energy measured across runs of consecutive replies and divided it by the total number of output tokens. The K26 module’s power sensor covers both the CPU and the FPGA. The readings include gaps between requests and time spent checking the answers, so background activity can affect the estimate.

The opening and closing profiles use the same timings. We convert module energy into electricity cost using the UK business average and sterling exchange rate for April–June 2026.[@uk-business-electricity; @uk-sterling-dollar] The memory figures come from the K26’s DDR4 specification.[@our-board-system]

</details>

<!-- scene: measure-autonomous -->

### 1. Let the FPGA choose the next token

**Skip work**

Our original circuit sent all 320 scores to the CPU. Even on the same chip, copying those scores across the wire bus takes clock cycles. The CPU then had to find the highest score and send its token ID back. The FPGA needed that ID as its next input, so every round trip delayed the next prediction.

In our first experiment, the FPGA chose the token itself. The scores are calculated one at a time. One register in the CLB logic holds the best score so far. Another holds its token ID. The CLB logic compares each new score with the saved one. If it is higher, the FPGA updates both registers. After the last score, it uses the saved ID to look up the token’s embedding and start the next prediction.

We expected this to save time because the FPGA compares each score while it calculates the rest. By the time the last score arrives, only one comparison remains. The CPU can send the prompt once and collect the reply. The whole change, including buffers for the prompt and reply, used 1,446 more LUTs and 2,671 more flip-flops. It used the same 10 DSPs and 36.5 BRAM tiles. Across all three prompts, decode speed rose from 205 to 251 tokens per second. A complete reply took 545 ms on average, down from 671 ms.

<!-- scene: measure-skip -->

### 2. Skip unused next-token scores

**Skip work**

Take the prompt `Hello`. After processing `H`, our FPGA used to calculate all 320 next-token scores even though `e` was already waiting. We changed the controller, which tells the FPGA which step to run next. It is built from LUTs and flip-flops spread across several CLBs. The FPGA still saves each token’s key and value in the KV cache after running the attention block. When another prompt token is waiting, the controller skips scoring and moves straight to that token. After `o`, it starts the scoring circuit to choose the first token of the reply.

Across all three prompts, the average wait for the first token fell from 125 to 108 ms. After that, every prediction was needed, so decode speed maintained at 251 tokens per second, as expected. We still needed the scoring circuit, so DSP and BRAM use stayed the same.

<!-- scene: measure-multiply -->

### 3. Multiply four bits at a time

**More work per tick**

The DSPs we introduced earlier multiply our 16-bit inputs and weights. Some other calculations, including normalisation, use wider, 64-bit numbers. We handle these with a separate multiplication circuit, using CLBs to control the steps and hold intermediate results.

Our original circuit checked one binary digit of an input per clock cycle, starting from the right. For example, `13` is `1101` in binary, or `8 + 4 + 1`. To calculate `5 × 13`, it added `5`, skipped `10`, added `20`, then `40`, giving `65`. The possible contribution doubles at each step because each binary digit is worth twice as much as the one to its right.

We built a larger multiplication circuit that processes four binary digits per clock cycle. It uses additional DSP blocks and LUT logic to calculate each contribution and combine it with the saved partial result, reducing the multiplication from 64 steps to 16. The input numbers and final answer stayed the same. The total DSP count rose from 10 to 30. Each time the model needed one of these products, it saved 48 clock cycles. Decode speed rose from 251 to 318 tokens per second.

<!-- scene: measure-divide -->

### 4. Divide two bits at a time

**More work per tick**

We applied the same idea to division. Our original divider worked like long division in binary, finding one binary digit of the answer per clock cycle. We built a larger circuit that finds two digits per cycle, reducing a 64-bit division from 64 calculation steps to 32. The answer and the rounding at the end stayed the same.

This used 540 more LUTs and 284 more flip-flops, with the DSP count still at 30 (our division does not use DSPs). The average time for a complete reply fell from 410 to 308 ms.

<!-- scene: measure-score-pipeline -->

### 5. Read the next weight while adding

**More work per tick**

After the final normalisation, the model’s scoring layer turns its 32 working values into 320 scores, one for each possible next token. Each score is a weighted sum with its own set of learned weights, like the sum we built earlier.

Our original scoring circuit alternated between reading and calculating. It read an input and its weight from memory, multiplied them and added the product to a running total. It then read the next pair. During each read cycle, the DSP circuitry had no new pair to work on.

But reading the next pair does not depend on finishing the current addition. We changed the controller to fetch the next input and weight while the DSP circuitry multiplied the current pair and added its product to the running total. The next pair could then be ready for the following clock cycle, allowing the arithmetic to continue sooner.

This change to the final scoring layer increased the complete FPGA design’s resource use by 14 LUTs and 11 flip-flops, with the same number of DSP blocks. Decode speed rose from 422 to 461 tokens per second, with exactly the same answers.

We reuse this technique later in the feed-forward block in experiment 9 and for attention’s KV-cache reads in experiment 10.

<!-- scene: measure-two-lanes -->

### 6a. Calculate two scores side by side

**More work per tick**

Each of the 320 token scores is a weighted sum of the same 32 input numbers, using a different set of learned weights. In our [neuron example](#fpga-neuron), one DSP multiplied each input by its weight and added the product to a running total in a *lane*. With one lane, the scoring circuit finishes one score before starting the next.

We added a second lane with its own running total, using one more DSP. We split the existing weights between two independently readable memory banks: one for odd-numbered scores, one for even-numbered scores. The two lanes could now calculate different scores at the same time, using the same inputs but reading different weights.

BRAM comes in fixed-size blocks, and the two smaller banks fitted those blocks less efficiently, leaving more unused space. This increased the BRAM total from 36.5 to 38 tiles. Decode speed rose from 461 to 485 tokens per second.

<!-- scene: measure-four-lanes -->

### 6b. Give four scores a lane each

**More work per tick**

We gave the scoring layer four lanes so it could work on four possible next tokens at once. As with the two-lane experiment, we compared it with the original one-lane scoring circuit.

All four lanes read the same input value. Each reads its own weight from a separate memory bank and adds the product to its own running total. By the time the inputs have passed through once, four scores are ready.

With three extra DSPs, final scoring took a little over a quarter of the clock cycles it had needed with one lane. The earlier stages still took just as long, so decode speed rose from 461 to 498 tokens per second.

<!-- scene: measure-eight-lanes -->

### 7. Double the lanes again

**More work per tick**

Would doubling the lanes again give us another gain? We built an eight-lane scoring circuit and compared it directly with the four-lane version.

Four more DSPs and four more independently readable banks of weights let us score eight possible tokens together. That nearly halved the time spent on final scoring. By now, though, the FPGA spent most of each prediction in the earlier stages of the transformer. Decode speed rose only from 498 to 505 tokens per second. We kept the eight lanes and turned to those earlier stages.

<!-- scene: measure-feedforward-divide -->

### 8. Shorten a division in the feed-forward stage

**Skip work**

In the feed-forward block, the model decides how much of each intermediate value to pass on. We shortened a division it repeats for every value.

Part of the calculation always divides by 45,426. Think of long division on paper. If the divisor is larger than the first few digits you have read, it goes into them zero times. You can carry those digits forward and bring down the next one. Our circuit checked for that case and went straight to the first digit that could be non-zero.

Repeating that small saving across the feed-forward block cut the average time for a complete reply by about 10%. The answers stayed the same and the divider needed no extra DSPs or BRAM.

<details>
<summary>Where does 45,426 come from?</summary>

Our circuit calculates an exponential using a small table of stored numbers. It splits the input into multiples of the natural logarithm of two and a remainder. In the circuit’s fixed-point format, one unit is stored as 65,536. The natural logarithm of two is about 0.69315, which becomes 45,426 at that scale.

</details>

<!-- scene: measure-down-pipeline -->

### 9. Overlap reads in another weighted sum

**More work per tick**

We applied the read-ahead trick from token scoring to the last part of the feed-forward block. This is where the model combines its 128 intermediate values into 32 weighted sums.

The FPGA used to multiply a value by its weight, add the product to the running total and only then ask for the next weight. We changed the controller to ask while the addition was under way. The same DSPs spent fewer clocks waiting for data, and the average time for a complete reply fell from 239 to 227 ms.

<!-- scene: measure-cache-pipeline -->

### 10. Read ahead in the KV cache

**More work per tick**

We let the FPGA read ahead in the KV cache. This time it was fetching parts of earlier tokens’ keys and values from BRAM.

An attention head compares the current query with each key, then mixes the cached values according to those comparisons. In both calculations the controller could ask for the next number while the DSP multiplied and added the current one. A longer prompt fills more of the cache, giving us more reads to overlap. The average wait for the first token fell from 46.4 to 44.4 ms, with the largest saving on the longest prompt.

<!-- scene: measure-attention-divide -->

### 11. Reuse the division shortcut in attention

**Skip work**

We found another use for the division shortcut from experiment 8. This time it helped attention decide how much each cached token should contribute.

Comparing a query with a key gives an attention score. An exponential turns that score into a positive number, whose share of the total determines how much of the token’s value goes into the mix. Calculating the exponential uses the same fixed divisor as in the feed-forward block. Again, the divider could skip steps whose answer was already known to be zero.

Each new query meets more keys as the cache fills, so longer prompts give the shortcut more chances to save time. Complete replies took about 15% less time on average, with exactly the same attention weights.

<!-- scene: measure-lutram -->

### 12. Move one set of weights into the logic blocks

**Weight storage and reads**

In [experiment 5](#fpga-measure-score-pipeline), we saved time by asking for the next weight earlier. Here we moved one set of weights from BRAM into the logic blocks and kept the timing of every read the same.

We chose the weights that combine the attention heads’ outputs. They fitted in distributed RAM, the small memories we can make from LUTs inside CLBs. Each weight still reached the multiplier on the same clock tick, so each reply took exactly as many cycles as before. What changed was the space we used. We freed one 18-kilobit BRAM block at the cost of 397 extra LUTs.

<!-- scene: measure-exp-pair -->

### 13. Work on two attention scores at once

**More work per tick**

We returned to the circuit from experiment 11 and let one attention head work on two scores at once. The number of heads stayed the same.

We added a second copy of the exponential circuit with its own lookup table. Both circuits could now take a score from the same head, then pass their results into the sum in the original order. At the first position there is only one score. As the KV cache fills, there are more pairs to work on together. Complete replies took about 6% less time on average.

The original circuit and this one both drew just over 3 watts at the module supply while running the replies. A watt is a joule per second. Finishing the same replies sooner brought module energy per output token down from about 0.020 joules at the start to 0.0051 here.

<!-- scene: measure-ddr-weight -->

### 14. Fetch an attention weight from outside the chip

**Weight storage and reads**

Our tiny model’s weights fitted on the FPGA, but a larger model might need the board’s DDR4 memory. Starting from experiment 13, we tested how much longer a reply would take if the FPGA fetched the weights that combine the attention heads’ outputs from DDR4.

We kept a copy in BRAM so we could try both sources with the same circuit. For each DDR4 read, the FPGA sent an address and waited for the memory controller to return the data. Four neighbouring weights arrived together. Our circuit used the one it had asked for, then sent another request for the very next weight.

Across our three prompts, complete replies took 22–27% longer with DDR4. The FPGA’s counters traced all the extra clock cycles to waiting for these weights.

<!-- scene: measure-ddr-row -->

### 15. Bring back a whole row of weights

**Weight storage and reads**

We kept the same weights in DDR4 and changed how we asked for them. We tried keeping the neighbouring weights that came back with each read, then fetching a whole row in one request.

First we gave the FPGA room to hold all four weights from a transfer. The multiplier could use them in turn before asking for more. Then we asked for a whole row of 32 weights. The memory controller sent the row in several transfers, but the FPGA only had to send the address once.

For `Hello`, fetching whole rows brought the reply down to 104 ms, compared with 103 ms using BRAM. Most of the delay in experiment 14 had come from repeatedly asking for data.

<!-- scene: measure-ddr-scores -->

### 16. Make room on the FPGA

**Weight storage and reads**

So far we had kept a BRAM copy of the weights so we could switch back to it. We went back to experiment 13 and moved the final scoring layer’s weights out of BRAM altogether.

The scoring weights now lived in DDR4. Each of the eight scoring lanes needs the weights for a different possible token. The FPGA fetched enough weights for eight scores into a small buffer, then let the lanes work through them. It could reuse that space for the next group of scores.

Moving the scoring weights freed eight BRAM tiles, even after allowing for the buffer. The lanes had to wait for each group of weights to arrive, so complete replies took 5–12% longer than with on-chip weights.

<!-- scene: measure-ddr-prefetch -->

### 17. Fetch the next group while scoring this one

**More work per tick**

We kept the scoring weights in DDR4 and started fetching the next group while the lanes were still using the current one.

We added a second buffer. While the lanes read weights from the first, the memory controller filled the second. When the lanes finished, the buffers swapped jobs. The FPGA fetched the same number of bytes, but the lanes spent less time waiting.

For `Hello`, the reply fell from 115 to 112 ms. We kept the saving of eight BRAM tiles, though on-chip weights were still faster for this model.

<!-- scene: measure-probability-div -->

### 18. Use the size of the answer to shorten division

**Skip work**

We returned to the faster on-chip circuit from experiment 13. We shortened the division that works out each token’s share of attention by using something we know about the answer in advance.

Suppose the positive numbers for three tokens are 2, 3 and 5. The first token’s share is 2 out of 10. Even a token that gets the whole share can have at most one. In the number format we use for these shares, one is stored as 32,768, so every possible answer fits in 16 bits.

Our general divider worked through a 64-bit answer two bits at a time. Here the first 48 bits of the answer were always zero. We gave the divider the remainder it would have reached after those steps, so it could start directly on the last 16 bits. That cut the division from 32 steps to eight, with the same rounding. Complete replies took 5–8% less time, with the biggest gain on the longest prompt.

<!-- scene: measure-feedforward-multiply -->

### 19. Build a faster multiplier for the feed-forward block

**More work per tick**

We built a faster multiplier for the wide numbers in the feed-forward block. The model uses these multiplications repeatedly to decide how much of each intermediate value to pass on.

The multiplier from experiment 3 worked through one number four bits at a time. This time we split both numbers into pieces and used DSPs to multiply every pair of pieces in parallel. The circuit then lined up the products by place value and added them, just as we line up the tens and units in long multiplication.

Each full product took five calculation clocks instead of 16. The design used 12 more DSPs, and complete replies took 7–9% less time.

<!-- scene: measure-norm-multiply -->

### 20. Speed up normalisation too

**More work per tick**

We used the faster multiplier from experiment 19 in another part of the model. We gave each of the three normalisation stages its own copy.

Normalisation adjusts the scale of the model’s working numbers. It squares each number by multiplying it by itself, then uses multiplication again to apply the scale it has worked out. Each of those products could now finish sooner. Across our three prompts, complete replies took 6–8% less time. Fitting all three multipliers brought the DSP count from 53 to 89.

<!-- scene: measure-norm-share -->

### 21. Let three stages share one multiplier

**Share hardware**

We let all three normalisation stages share one fast multiplier. They already ran at different times, so we expected one multiplier to keep up with all three.

The first stage runs before attention, the second before the feed-forward block and the last before scoring. Whichever stage was active sent its two numbers to the shared multiplier and collected the product. The other stages had no multiplication waiting. Each reply took exactly the same number of FPGA clocks as before, and the whole design used 57 DSPs instead of 89.

<!-- scene: measure-projection-reads -->

### 22. Read ahead wherever a weighted sum still waits

**More work per tick**

We looked for weighted sums that still waited for a read before starting the next calculation. We tried reading ahead in each part of the model separately, then combined the changes.

In attention, we fetched the next input and weight while adding the current product. The model reads weights to calculate the query, key and value. Later it reads another set of weights to combine the heads’ outputs. Reading ahead helped at both points. We tried the same change in the two weighted sums at the start of the feed-forward block. Those sums already ran alongside other calculations, so finishing them sooner barely changed when the block could move on.

The separate simulations showed that nearly all the saving came from attention. With the changes combined on the board, complete replies took 8–10% less time, using the same DSPs.

<!-- scene: measure-value-pair -->

### 23. Mix two parts of a cached value at once

**More work per tick**

We let each attention head mix two parts of a cached value at once. Both parts use the same token’s share of attention, and each has its own running total.

Suppose a token gets a quarter of the attention. We need a quarter of its first number and a quarter of its second. We put the first number in one BRAM bank, the second in another, and alternated banks for the rest of the value. The FPGA could now read two neighbours together. Each lane multiplied its number by the token’s share and added the product to its own total.

The design used one more DSP and the same amount of BRAM. Complete replies took 4–7% less time, with the biggest gain on the longest prompt because it had more cached values to mix.

<!-- scene: measure-clock-rate -->

### 24. Run the same circuit on a faster clock

**Faster clock**

Until now we had kept the clock at 50 MHz and tried to do the work in fewer ticks. For the last experiment we kept exactly the circuit from experiment 23 and turned up its clock.

At 52.63 MHz the time between ticks fell from 20 to 19 nanoseconds. Each reply took exactly the same number of ticks, so it finished about 5% sooner. The module drew slightly more power while it worked, but used 4.6% less energy per output token across the three prompts.

Could we go faster still? At 62.5 MHz a signal would have only 16 nanoseconds to pass through the logic and reach the next flip-flop. Vivado’s timing check found that the slowest path would miss that deadline even after it tried a different layout. We kept that setting off the board.

Our first 23 experiments kept the FPGA clock at 50 MHz. Once the FPGA chose each token itself, it could start the next prediction without waiting for the CPU. We shortened multiplication and division, read the next weight while adding the current product and calculated several scores side by side. With fewer clock ticks between tokens, decode speed rose from 205 to 805 tokens per second across our three prompts by experiment 13. Later, fetching whole rows from DDR4 let us trade a little speed for room on the chip, and sharing a multiplier freed DSPs without costing a clock. By experiment 22, the board could finish its reply to `Hello` in 75 ms. Mixing two coordinates of each cached value in parallel and then shortening the clock cycle brought that down to 68 ms. The model gave exactly the same replies.

<!-- scene: chip-choices -->

### Choosing a chip for inference

These charts use the same axes as above. We measured inference on our FPGA and estimated speed and energy for its Arm CPU, the NVIDIA H100 and Google’s TPU v5e using the same model and prompts.

Our FPGA and CPU share DDR4 memory.[@our-board-system; @our-board-processors] The H100 and TPU each have their own high-bandwidth memory.[@h100-memory; @tpu-v5e-memory] The charts show peak memory bandwidth and how many `16-bit` weights would fill the memory. In practice, each request also needs room for a KV cache that grows with the prompt and reply.

With an FPGA, we can change what the logic blocks do and how they connect. CPUs, GPUs and TPUs have fixed circuitry, ranging from general-purpose designs to chips specialised for neural network maths.[@fpga-asic; @cpu-gpu]

We built a transformer that tells chip jokes so we could keep its answers fixed and change the machine underneath it. AI helped us write circuit changes and run the same checks over and over. We could try two ways to mix a cached value, check both against the software model and let the board tell us which was faster. Across our three prompts, the same FPGA went from 205 to 1,222 tokens per second and gave the same replies.

We still don’t know where those curves flatten. We’ll keep changing one part at a time to see when the wait for the first token, the speed of the reply and the energy per token stop improving by more than we see between repeat runs. Then we’ll try the largest model we can run on this board. One candidate is the text part of Qwen3.5-0.8B.[@qwen-35-small] We’ll optimise it and run the same model and prompts on other chips. Then we can replace the grey estimates above with measurements.
