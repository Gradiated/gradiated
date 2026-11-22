# Lecture 4 — Inside our FPGA: How a chip runs a tiny language model

## What are we trying to get across?

- **Reconfigure the chip.** Stored settings choose the logic and connections.
- **Follow one token.** Watch the arithmetic and data movement.
- **Test the trade-offs.** Circuit and memory choices change speed and energy.

**Presentation website:** [Open the Lecture 4 slides](http://127.0.0.1:5182/lectures/lecture-4/). Keep this script open alongside the slides. Use the left contents or the arrow keys to move through the figures.

**For future sessions:** if the preview is closed, restart the local server using the [saved website instructions](../../../../../product/website/lectures/README.md#lecture-4--inside-our-fpga).

## Introduction

### 01. [Inside our FPGA](http://127.0.0.1:5182/lectures/lecture-4/#cover)

- Last time we went from wafer to circuit. What if we could change its job after fabrication?
- We’ll configure a gate, build up to a tiny language model, and look briefly at how an FPGA runs it. 

### 02. [How would we compare this chip?](http://127.0.0.1:5182/lectures/lecture-4/#fpga-inference-profile)

I THINK THE GOAL OF THIS UNDERTAKING IS TO COME UP WITH A STANDARDISED WAY OF COMPARING CHIPS AND A SORT OF EXPERIMENTAL METHOD OF FINDING BOTTLENECKS AND WAYS TO IMPROVE THINGS, especially leaning on the fact that we can now do loads of iterative experimentation by just linking this to codex.
- **Point to our AMD Kria KV260.** The outline introduces what to compare. The spokes here are placeholders.

## A chip that can change its job

### 03. [A chip that can change its job](http://127.0.0.1:5182/lectures/lecture-4/#fpga-reconfigure)

- The FPGA comes with logic blocks, wires and switches (LIKE TRAIN RAILS) already manufactured.
- Settings choose the logic and connections.

### 04. [Pins connect to the outside world](http://127.0.0.1:5182/lectures/lecture-4/#fpga-map-io)

- I/O blocks send and receive signals through pins.
- Interfaces can work in parallel. Speed depends on the design.
- FPGAS TEND TO HAVE LOADS OF IO FOR LOADS OF SIGNAL

### 05. [Configurable logic blocks](http://127.0.0.1:5182/lectures/lecture-4/#fpga-map-logic)

- Logic blocks compute and hold results.
- Connect them to build bigger circuits.

### 06. [Wires between blocks](http://127.0.0.1:5182/lectures/lecture-4/#fpga-map-routing)

- Wires carry signals between blocks and pins.
- The chip comes with these wire segments already in place. 

### 07. [Switches choose the connections](http://127.0.0.1:5182/lectures/lecture-4/#fpga-map-junctions)

- Point to junctions. Stored bits choose which wires connect.
- TRAIN RAILWAY TRACKS
- The circuit is the blocks plus the selected paths.

### 08. [Our first circuit](http://127.0.0.1:5182/lectures/lecture-4/#fpga-first-circuit)

- Trace A and B through the logic block to the output.
- AND with A = 1, B = 1 gives 1.

### 09. [Change an input](http://127.0.0.1:5182/lectures/lecture-4/#fpga-input-change)

- Flip B to 0. AND now gives 0.
- The rule and routing stay fixed.
- incredibly wasteful use of an fpga

## Why use an FPGA?

### 10. [Filter particle collisions](http://127.0.0.1:5182/lectures/lecture-4/#fpga-why-fpgas)

- CERN detectors send many streams at once.
- The FPGA quickly chooses which events to keep.
- SO HELPS WITH VAST AMOUNT OF FAST DATA, loads of Inputs 

### 11. [Drive a wall of LEDs](http://127.0.0.1:5182/lectures/lecture-4/#fpga-why-display)

- Point to the LED tiles. Send pixels in parallel and sync the updates.
- Keep the old picture up while preparing the next.
- FAST AND VAST DATA, loads of outputs

### 12. [Prototype a custom chip](http://127.0.0.1:5182/lectures/lecture-4/#fpga-why-prototype)

-WE CAN RECREATE THE LOGIC BLOCKS OF THE ASIC ON THE FPGA - THEY WILL PHYSICALLY BE DIFFERENT BUT PERFORM THE SAME WAY.
- Test and reload fixes on the FPGA. This is functional verification.
- The ASIC has its own speed and power.
- CONFIGURABLE IS PRO

## Inside a logic block

### 13. [Zoom into a logic block](http://127.0.0.1:5182/lectures/lecture-4/#fpga-inside-chip)

- Zoom into a configurable logic block (CLB). It computes and holds bits.

### 14. [What fits inside a logic block?](http://127.0.0.1:5182/lectures/lecture-4/#fpga-clb-resources)

- LUTs select answers. Flip-flops hold results.
- This UltraScale CLB has 8 LUTs and 16 flip-flops.

### 15. [One look-up table and one flip-flop](http://127.0.0.1:5182/lectures/lecture-4/#fpga-inside-clb)

- Follow the LUT answer into the flip-flop. The clock captures it.

### 16. [Four possible input combinations](http://127.0.0.1:5182/lectures/lecture-4/#fpga-truth-table)

ITS A BLOCK THAT TAKES 2 INPUTS AND LEAVES AS OUTPUT 1 BIT. BUT IT NEEDS TO KNOW WHAT LOGIC FUNCTION IT SHOULD PERFORM, SO WE NEED TO TELL IT. 
- Two inputs, four rows. One SRAM bit per answer.
- AND gives 1 only at 11. A = 1, B = 0 selects 10.

### 17. [Follow a bit through the selectors](http://127.0.0.1:5182/lectures/lecture-4/#fpga-selector)

- B picks within each pair. A picks the pair.
- Trace 01 to its stored answer, 0.
- EXPLAIN THAT ITS AN AND
  
## Writing the stored rule

### 18. [How SRAM holds one answer](http://127.0.0.1:5182/lectures/lecture-4/#fpga-stored-bit)

- Two NOT gates feed back and hold opposite values.
- Point to the access transistors. Access off holds the stored 0.

### 19. [Write a new answer](http://127.0.0.1:5182/lectures/lecture-4/#fpga-write-and-hold)

- Set opposite voltages on the write wires. Enable access.
- The wires set the cell from 0 to 1.

### 20. [Keep the new answer](http://127.0.0.1:5182/lectures/lecture-4/#fpga-cell-hold)

- Turn access off. Feedback holds 1 while powered.
- No refresh needed. Power off loses the bit.

### 21. [Turn AND into OR](http://127.0.0.1:5182/lectures/lecture-4/#fpga-lut)

- Change rows 01 and 10. AND 0001 becomes OR 0111.
- Each extra input doubles the answers. Six inputs need 64 bits.

## Keeping a result

### 22. [A result is waiting](http://127.0.0.1:5182/lectures/lecture-4/#fpga-flip-flop)

- Point to LUT output 1 and saved output 0. Wait for the clock edge.
- A flip-flop remembers a single 0 or 1 and updates it when the circuit’s clock tells it to. ACTS AS A BUFFER 


### 23. [Capture the result on a clock edge](http://127.0.0.1:5182/lectures/lecture-4/#fpga-logic-block)

- Clock edge captures the LUT’s 1.
- The next circuit uses the saved 1 while the LUT works again.
- CLOCK IS BASICALLY THE CONDUCTOR, AND CALCULATIONS ALL GET READY BEFORE THEM, THEN WHEN CYMBALS STRIKE THEY ARE SHUFFLED TO THEIR NEXT CALCUALTION, SO THAT ALL THE FLOW CAN BE CONTROLLED.

### 24. [Hold the last result](http://127.0.0.1:5182/lectures/lecture-4/#fpga-flip-flop-hold)

- Pause the clock. LUT output goes to 0. Saved output stays 1.

### 25. [Choose the direct or saved result](http://127.0.0.1:5182/lectures/lecture-4/#fpga-clb-output-setting)

- Output MUX selects the direct or saved result.
- SRAM holds the setting. The flip-flop holds data.

## Choosing the connections

### 26. [Join two logic blocks](http://127.0.0.1:5182/lectures/lecture-4/#fpga-routing-grid)

- Trace both sources along built-in wires. Open the junction.

### 27. [Open a routing switch](http://127.0.0.1:5182/lectures/lecture-4/#fpga-routing-switch)

- Two wires in, one out. Setting 0 selects the upper wire carrying 1.

### 28. [Select a different wire](http://127.0.0.1:5182/lectures/lecture-4/#fpga-routing-change)

- Write setting 1. The switch selects the lower wire carrying 0.

### 29. [Send new data down the same wire](http://127.0.0.1:5182/lectures/lecture-4/#fpga-routing-input)

- Lower source changes from 0 to 1. The selected route stays fixed.

### 30. [From one setting to a whole chip](http://127.0.0.1:5182/lectures/lecture-4/#fpga-configuration-map)

- Zoom out from one setting to a chip full of logic and routing settings.

## Configuring the whole chip

### 31. [Load a bitstream](http://127.0.0.1:5182/lectures/lecture-4/#fpga-configuration-source)

- The bitstream holds FPGA settings. Flash can store it without power.
- At startup, load the settings across the FPGA.

### 32. [Send a setting to the routing](http://127.0.0.1:5182/lectures/lecture-4/#fpga-configuration-distribute)

- Trace the setting to the routing MUX. Stored 0 keeps the upper wire selected.

### 33. [Load the LUT answers](http://127.0.0.1:5182/lectures/lecture-4/#fpga-configuration-luts)

- Point to AND, OR, NOR and NAND. Each LUT gets its own answer bits.
- The animation writes one bit at a time. Hardware loads groups.

### 34. [Distribute the clock](http://127.0.0.1:5182/lectures/lecture-4/#fpga-clock-network)

- A dedicated network carries clock edges to the flip-flops.
- Buffers and routing reduce clock skew (differences in arrival time).

## Memory and arithmetic

### 35. [Make room for working data](http://127.0.0.1:5182/lectures/lecture-4/#fpga-resources-map)

- Some LUTs become distributed RAM.
- Dedicated BRAM holds more data and frees up logic blocks.

### 36. [Read and write block RAM](http://127.0.0.1:5182/lectures/lecture-4/#fpga-block-ram)

- Pick one of four addresses. Each holds four bits.
- Pause and pick a value. Write enable + clock edge saves it.

### 37. [Find the arithmetic blocks](http://127.0.0.1:5182/lectures/lecture-4/#fpga-arithmetic-map)

- Point to the DSP. Its built-in multiplier and adder save LUTs.

### 38. [Multiply two numbers](http://127.0.0.1:5182/lectures/lecture-4/#fpga-arithmetic-blocks)

- Trace 3 × 2 = 6 through the DSP.
- Configuration connects the multiplier to our circuit.

### 39. [Prepare a running total](http://127.0.0.1:5182/lectures/lecture-4/#fpga-arithmetic-accumulate)

- The adder gives 0 + 6. The register still holds 0.
- Ask where 6 goes on the next edge.

### 40. [Save the running total](http://127.0.0.1:5182/lectures/lecture-4/#fpga-arithmetic-save)

- Clock edge saves 6. Feed that total back into the adder.

### 41. [Add the next product](http://127.0.0.1:5182/lectures/lecture-4/#fpga-arithmetic-next)

- Next product is 2 × 2 = 4. Add it to the saved 6.
- Clock edge saves 10. Same multiplier, adder and register.

### 42. [Follow a calculation across the chip](http://127.0.0.1:5182/lectures/lecture-4/#fpga-pins)

- Trace input pin → CLBs → BRAM → DSP → output pin.
- CLBs choose the numbers. BRAM supplies them. DSP updates the total.

### 43. [Memory has several jobs](http://127.0.0.1:5182/lectures/lecture-4/#fpga-memory-roles)

- Configuration SRAM holds settings. Flip-flops hold results.
- Distributed RAM and BRAM store working data. Our initial inference design also reads its learned weights from BRAM. 

### 44. [A chip full of specialised blocks](http://127.0.0.1:5182/lectures/lecture-4/#fpga-resource-columns)

- Point to columns of logic, memory and DSPs. The mix varies by chip.
- Wires move data. The clock coordinates when results are saved.

## Our FPGA’s first neuron

### 45. [Our extremely overfitted transformer](http://127.0.0.1:5182/lectures/lecture-4/#fpga-neuron-map)

- Reuse these blocks to predict the next piece of text (token).
- IM GOING TO ZOOM INTO THIS PART (ONE NEURON) AND THIS PART (KV CACHE)

### 46. [Zoom into a weighted sum](http://127.0.0.1:5182/lectures/lecture-4/#fpga-network-sum)

- Point to inputs 3 and 2. Multiply by their weights, 2 and −1.

### 47. [Two products, one sum](http://127.0.0.1:5182/lectures/lecture-4/#fpga-network-products)

- Add the two products, 6 + (−2) = 4.
- New inputs reuse the learned weights.

### 48. [Map the sum onto hardware](http://127.0.0.1:5182/lectures/lecture-4/#fpga-neuron-hardware)

- BRAM supplies numbers. CLBs pick pairs. DSP multiplies and adds.
- Each pair takes a turn through the same circuit.

### 49. [Save the first product](http://127.0.0.1:5182/lectures/lecture-4/#fpga-neuron)

- Read 3 and 2. Multiply, add to 0, then save 6 on the clock edge.


### 50. [Add the second product](http://127.0.0.1:5182/lectures/lecture-4/#fpga-neuron-next)

- Read 2 and −1. Add their product (−2) to 6. Save 4.
- This is one of many weighted sums in the model.
- FINAL PRODUCT GIVES NODE ACTIVATION

## Running a tiny transformer

### 51. [Now where does KV cache go?](http://127.0.0.1:5182/lectures/lecture-4/#fpga-transformer-cache-map)

- Follow the zoom to BRAM. Store a key and value for each token.
- Key helps decide how much to use. Value supplies what gets mixed in.

### 52. [Save the keys and values](http://127.0.0.1:5182/lectures/lecture-4/#fpga-transformer-cache)

- WE WANT TO FOR EACH TOKEN, MULTIPLY BY KEY AND VALUE MATRIX, AND SAVE THOSE VECTORS AS A LIST OF NUMBERS IN THE KV CACHE, BECAUSE WE DONT WANT TO CALCULATE THOSE VALUES AGAIN.
- Cache grows 128 bytes per token. Weights stay fixed.

### 53. [From a to R to Re](http://127.0.0.1:5182/lectures/lecture-4/#fpga-token-journey)

- Prompt `a` picks `R`. Feed `R` back and get `e`.
- Design returns 320 scores. CPU picks the highest and sends back that token.
- ARBITRARY BOTTLENECK, THIS IS FOR LATER EXPERIMENTS I WILL DO WHERE I WANT TO MEASURE HOW MUCH TIME AND ENERGY WE SAVE BY AVOIDING ONE ROUND TRIP TO THE CPU PER TOKEN
  - cpu just does argmax finds highest score.

### 54. [What is on the KV260?](http://127.0.0.1:5182/lectures/lecture-4/#fpga-our-board)

- **CPU** runs Linux, sends tokens and picks the next one.
- **FPGA** runs the maths. BRAM holds weights and KV cache.
- **Token arrow** sends an ID to the FPGA.
- **Scores arrow** returns scores to the CPU.
- **Controllers** handle transfers to memory and storage.
- **DDR4** holds running programs and data.
- **Boot flash** keeps startup code without power.
- **microSD** holds Linux and app files.
- **Ethernet** carries prompts and replies.

### 55. [Follow a request through the board](http://127.0.0.1:5182/lectures/lecture-4/#fpga-board-request)

- **Boot.** Flash starts the board. Linux loads from microSD into DDR4 and runs on Arm.
- **Request.** Trace laptop → Ethernet → Arm → FPGA and back.
- **Work split.** Arm loads weights and picks tokens. FPGA does the maths and holds the KV cache.
- **What ran.** The shown reply is from software. The measured experiments at the end use the text-input model running on the KV260.
- **Say:** “We can reuse one adder to save space or use more of the chip to do several additions at once if memory keeps up, then measure the effect on tokens per second and energy per token.”

## Choosing a chip

### 56. [Choose the chip for the job](http://127.0.0.1:5182/lectures/lecture-4/#fpga-chip-choices)

MENTION IP BLOCK WHEN WE GET TO THE TAKES TIME TO DESIGN AND VERIFY? BIT.
- THIS USED TO BE A BIG DEAL, BUT NOW IT SEEMS SO EASY TO BIULD THIS PART WHICH IS BASICALLY JUST SOFTWARE TESTING ON HARDWARE THAT IS RIGHT THERE AND IS VERIFIABLE, THAT WE CAN PROBABLY BEAT THIS NOW OR RECREATE IT.
- **CPU** for varied software. **GPU/NPU** for parallel maths.
- **FPGA** for custom interfaces, timing and arithmetic. Reconfigure and verify.
- **ASIC** can pay off at high volume.

## Measuring inference on the KV260

### 57. [Experiments with inference on our FPGA](http://127.0.0.1:5182/lectures/lecture-4/#fpga-measuring-inference)

AI MAKES IT SUPER EASY NOW TO RUN LOTS OF LITTLE EXPERIMENTS, EVEN ON HARDWARE. AND FPGAS ARE THE PERFECT TESTING GROUND

- **Illustrative graph.** Blue = tokens/s. Dashed = cost/token. Walk through the four experiments.
- **Try more designs.** AI helps write and test variants. Try 1, 2, 4 or 8 multiply-add units.
- **One change at a time.** Same model and prompts. Check against the software reference.
- **Measure on the board.** First-token time, tokens/s, energy/token and estimated cost per million tokens.
- **What limits us?** Arithmetic, memory bandwidth or the CPU round trip?

Hoping that by doing this i learn alot. WANT TO LEARN WHAT KINDS OF CHANGES MAKE WHAT IMPROVEMENTS AND WHY, AND ESPECIALLY WHAT THINGS ARE EASIER NOW THAT WE CAN ITERATIVELY IMPROVE RELENTLESSLY WITH AI

### 58. [How far can we push this FPGA?](http://127.0.0.1:5182/lectures/lecture-4/#fpga-throughput-example)

HOW FAR CAN WE PUSH AI EXPERIMENTATION TO MAKE SMALLER AND SMALLER IMPROVEMENTS, WHAT ARE LIMITS? I WANT TO KNOW THEM

I.E. I WANT TO KNOW, FOR CERTAIN, THIS IS WHY WE WILL NEVER BE ABLE TO RUN KIMI K3 ON AN FPGA, OR MAYBE WE CAN WE JUST NEED A REALLY GOOD ONE ETC...

- **Point to the board.** “I want to push the FPGA on this table to its limits and measure what gives out first. How low can we get the cost per token while keeping the answers the same and the replies just as fast?”
- **Capacity.** Fit the largest model and its KV cache at a fixed context length and quality target. Then optimise speed.
- **Benchmarks.** Small model for speed. Larger model for energy per token.
- **Same conditions.** Model, prompts, token limits, batch size, quality and warm-up. Measure energy at the same boundary.
- **Spider charts.** Placeholder shapes. Use the same tests and scales for real comparisons.
- **Transition.** “Now let’s see what happened on this board.”

## Measured experiments

### 59. [Baseline: the CPU chooses the next token](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measured-baseline)

DESCRIBE EACH PART OF THIS FIRST FIGURE

- The FPGA calculates 320 scores and sends them all to the CPU. The CPU picks one token and sends it back.

### 60. [1. Let the FPGA choose the next token](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-autonomous)

- As each score arrives, the FPGA remembers the best one so far. Now it can choose the next token itself.

### 61. [2. Skip unused next-token scores](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-skip)

- When we read the H in Hello, we already know the next letter is e. We save what attention needs and wait until the o to score the next token.

### 62. [3. Multiply four bits at a time](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-multiply)

- The multiplier used to save its progress after each bit. Taking four bits at a time cuts 64 steps to 16.

### 63. [4. Divide two bits at a time](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-divide)

- The divider builds the answer two bits at a time. That cuts a 64-step division to 32 steps.

### 64. [5. Read the next weight while adding](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-score-pipeline)

- While the DSP adds this product to the score, memory fetches the next input and weight. The DSP spends less time waiting.

### 65. [6a. Calculate two scores side by side](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-two-lanes)

- Both lanes see the same input, but each reads its own weight and adds to its own score. One lane handles odd scores and the other handles even scores.

### 66. [6b. Give four scores a lane each](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-four-lanes)

- Now four scores advance on the same tick. Against the same one-lane starting point, decode speed rises from 461 to 498 tokens per second.

### 67. [7. Double the lanes again](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-eight-lanes)

- Eight lanes nearly halve scoring time again. The other layers now take most of the time, so decode speed only rises from 498 to 505 tokens per second.

### 68. [8. Shorten a division in the feed-forward stage](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-feedforward-divide)

- Here we always divide by the same number. If the first answer bits have to be zero, we can skip straight past them.

### 69. [9. Overlap reads in another weighted sum](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-down-pipeline)

- Each output combines 128 inputs. While we add one product, we fetch the next weight.

### 70. [10. Read ahead in the KV cache](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-cache-pipeline)

- Attention fetches the next cached key or value while it uses the current one. A longer prompt gives us more chances to save a wait.

### 71. [11. Reuse the division shortcut in attention](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-attention-divide)

- We can skip leading zeros in attention’s divider too. We save those steps every time we process an attention score.

### 72. [12. Move one set of weights into the logic blocks](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-lutram)

- We moved the weights that combine the heads from BRAM into LUT memory. The weights arrive on the same tick, so the memory bars change but the speed stays the same.

### 73. [13. Work on two attention scores at once](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-exp-pair)

- Within one attention head, two scores can go through the exponential calculation side by side. If there’s only one score ready, the second circuit waits.

### 74. [14. Fetch an attention weight from outside the chip](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-ddr-weight)

- DDR4 sends four weights together, but we use just one. For the next weight we have to ask again.

### 75. [15. Bring back a whole row of weights](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-ddr-row)

- Now one request brings back eight groups of four, and we use all 32 weights. Reading 1,024 weights now takes just 32 requests.

### 76. [16. Make room on the FPGA](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-ddr-scores)

- Moving the scoring weights to DDR4 frees eight BRAM tiles. We fetch just enough at a time to calculate eight candidate scores.

### 77. [17. Fetch the next group while scoring this one](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-ddr-prefetch)

- Buffer A feeds the scoring lanes while buffer B fills from DDR4. Then they swap jobs.

### 78. [18. Use the size of the answer to shorten division](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-probability-div)

- Divide one value by the sum of all the values, and its share can never exceed one. That lets us skip 48 leading zero bits and finish in eight steps.

### 79. [19. Build a faster multiplier for the feed-forward block](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-feedforward-multiply)

- We split each input into four pieces so the DSPs can multiply pairs of pieces in parallel. Even after we add the smaller products together, a multiplication takes five ticks instead of 16.

### 80. [20. Speed up normalisation too](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-norm-multiply)

- Each normalisation stage has its own multiplier. As each one lights up, the other two sit idle.

### 81. [21. Let three stages share one multiplier](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-norm-share)

- The same three stages take turns on one multiplier. The reply takes exactly as many ticks as before, and DSP use falls from 89 to 57.

### 82. [22. Read ahead wherever a weighted sum still waits](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-projection-reads)

- We fetch the next weight during more of the model’s sums, including those that form queries, keys and values. Together these changes save about 4,000 ticks per position.

### 83. [23. Mix two parts of a cached value at once](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-value-pair)

- One attention weight applies to two neighbouring numbers in the same cached value. Each lane multiplies its number by that weight and keeps its own sum.

### 84. [24. Run the same circuit on a faster clock](http://127.0.0.1:5173/lectures/lecture-4/#fpga-measure-clock-rate)

- Four ticks take 80 nanoseconds on the top trace and 76 on the bottom. The same replies finish about 5% sooner.

### 85. [The same FPGA, after 24 experiments](http://127.0.0.1:5173/lectures/lecture-4/#fpga-final-profile)

- On the same board, decode speed rose from 205 to 1,222 tokens per second. The model gave the same replies and used less energy per token.

### 86. [How would other chips run the same model?](http://127.0.0.1:5173/lectures/lecture-4/#fpga-chip-profiles)

- We measured the FPGA on the board. The other chip profiles are estimates until we run the same model and prompts on those chips.

**So what are the next steps for fpga? - bottleneck for this project is just I have to be physically hooked up to fpga. Need to get a better system where I dont have to be on my laptop - maybe fpga + raspberry pi and leave it in wework, and just keep optimising. fit largest model possible on this fpga. Then once thats done and optimised, I will come back and show you guys and we can discuss if it is worth buying a large serious fpga and doing the same.**

<details>
<summary>Full presenter notes and sources for slides 59–86</summary>

**59. Baseline: the CPU chooses the next token**

DESCRIBE EACH PART OF THIS FIRST FIGURE

- Start with the CPU choosing from 320 scores. The FPGA map shows where the work happens. On the left, read the bars as the share of the chip used and the three coloured points as first-token time, decode speed and module energy per output token.

**60. 1. Let the FPGA choose the next token**

- Follow the return arrow. Keeping the best score on the FPGA means the CPU no longer has to collect every score before the next token can start.

**61. 2. Skip unused next-token scores**

- Take the prompt `Hello`. After H we already know the next input is e. Save the key and value, then skip scoring until the final prompt token.

**62. 3. Multiply four bits at a time**

- The wide multiplier used to save its progress after each bit. Handling four bits between saves cuts 64 calculation steps to 16.

**63. 4. Divide two bits at a time**

- Division also builds up an answer. Finding two bits per clock halves the calculation steps while keeping the same rounding.

**64. 5. Read the next weight while adding**

- Follow the two active paths. The next weight can arrive while the DSP is still adding the current product.

**65. 6a. Calculate two scores side by side**

- Both lanes use the same input. One reads weights for odd-numbered scores and the other for even-numbered scores. Each keeps its own total.

**66. 6b. Give four scores a lane each**

- Four lanes work on four scores together. Compare this build with the same one-lane starting circuit used for the two-lane test.

**67. 7. Double the lanes again**

- Doubling the lanes again nearly halves scoring time, but decode speed only rises from 498 to 505 tokens per second. The other stages now take most of the time.

**68. 8. Shorten a division in the feed-forward stage**

- The feed-forward calculation repeatedly divides by the same number. When the first answer digits must be zero, the divider can start further along.

**69. 9. Overlap reads in another weighted sum**

- At the end of the feed-forward block we combine 128 values into 32 sums. Read the next pair while adding the current product, just as we did for scoring.

**70. 10. Read ahead in the KV cache**

- Attention can request the next cached key or value while it works on the current one. A longer prompt gives it more reads to overlap.

**71. 11. Reuse the division shortcut in attention**

- Each attention score goes through an exponential calculation. The same fixed-divisor shortcut saves work once for every score.

**72. 12. Move one set of weights into the logic blocks**

- Move the weights that combine the heads from BRAM into LUT memory. They arrive on exactly the same clock. The histogram changes even though the reply takes the same number of clocks.

**73. 13. Work on two attention scores at once**

- Start again from experiment 11. A second exponential circuit handles a second score alongside the first whenever the cache has a pair ready.

**74. 14. Fetch an attention weight from outside the chip**

- Each DDR4 transfer brings four weights, but the circuit uses only one. For Hello, the same reply takes 131 ms instead of 103 ms from BRAM.

**75. 15. Bring back a whole row of weights**

- Keep the other weights that arrive. Asking for whole rows cuts the number of requests for 1,024 weights from 1,024 to 32.

WE RECOVER ALL OF THE LOSS - COULD BE INTERESTING BECAUSE NOW WE HAVE MUCH MORE ACCESS TO LARGE MEMORY

**76. 16. Make room on the FPGA**

- Move the scoring weights off-chip. Point to the 20 KiB in DDR4 and the drop from 39 to 31 BRAM tiles. The lanes now wait for each group to arrive.

**77. 17. Fetch the next group while scoring this one**

- One buffer feeds the scoring lanes while the other fills from DDR4. We move just as many bytes, but hide some of the wait.

**78. 18. Use the size of the answer to shorten division**

- Return to the on-chip build from experiment 13. Each token’s share is at most one, so the high digits of the fixed-point quotient must be zero. Skip 24 division steps.

**79. 19. Build a faster multiplier for the feed-forward block**

- Split each wide input into four pieces. DSPs multiply pairs of pieces side by side, then the circuit adds their contributions in the right places.

**80. 20. Speed up normalisation too**

- Normalisation squares and rescales the working values. Giving all three normalisation stages faster multipliers reduces reply time but raises the DSP count to 89.

**81. 21. Let three stages share one multiplier**

- The three stages take turns. Sharing one multiplier gives the same answers in exactly the same number of clocks and brings the DSP count down to 57.

**82. 22. Read ahead wherever a weighted sum still waits**

- Read ahead in the weighted sums that produce the query, key and value and in the other projections. Across the model these changes save 3,999 clocks per processed position.

**83. 23. Mix two parts of a cached value at once**

- Read two neighbouring numbers from a cached value. Both use the same attention weight, and each lane keeps its own sum. The board completes replies 4–7% sooner than in experiment 22.

**84. 24. Run the same circuit on a faster clock**

- Use the two clock traces. At 50 MHz, four ticks take 80 nanoseconds. At 52.63 MHz, the same four ticks take 76. The board gave the same replies in the same number of ticks, so they finished about 5% sooner.
- Point to the graph. Decode speed rose from 1,161 to 1,222 tokens per second, and energy per output token fell 4.6% across the mixed prompts. We also tried a 62.5 MHz target in the design tools. The slowest signal would arrive about one nanosecond late, so we stopped before testing that setting on the board. [Board measurements](../../../../research/inference/results/attention-clock-20261120T004416Z-a9d9d2/run.json) · [Timing report](../../../../research/inference/results/attention-clock-v1-stretch-build-20261120T003806Z/run.json)

**85. The same FPGA, after 24 experiments**

- Follow the decode-speed spoke. The original circuit waited for the CPU to choose every token. By experiment 23 the FPGA chose its own tokens, fetched the next weights while it worked and ran several calculations side by side. That took us from 205 to 1,161 tokens per second at 50 MHz. The faster clock supplied the last step to 1,222.
- Further out means better, so a shorter wait for the first token moves its point outwards too. We used the same three prompts and checked the replies. The energy reading covers the module, including its background power. Finishing sooner means paying that background cost for less time.
- The two outlines meet on two spokes. We changed the circuit on the board. Both versions have the same DDR4 capacity and peak bandwidth. [Article figure and measurement method](http://127.0.0.1:5173/sand-to-thought/fpga/#fpga-final-profile)

**86. How would other chips run the same model?**

- Start with the CPU and FPGA. They sit on the same KV260 and share its DDR4. The CPU follows instructions. On the FPGA we could change the circuit itself, as we did when we put token selection beside the score calculation.
- The GPU and TPU have much higher peak memory bandwidth. Our tiny model’s weights already fit on the FPGA, so extra bandwidth alone tells us little about how soon the first token arrives.
- We measured inference on the FPGA. The three grey plots use assumed calculation rates, overheads and power for the same prompts, one request at a time. The GPU and TPU share those assumptions, which is why their inference spokes match. To rank the chips we would need to run the model on each and measure the same workload with a comparable power boundary. [Article comparison and assumptions](http://127.0.0.1:5173/sand-to-thought/fpga/#fpga-chip-choices)



</details>

## Sources and assets

- [FPGA article preview](http://127.0.0.1:5182/sand-to-thought/fpga/) · [Article source](../../articles/fpga/script.md) · [FPGA project notes](../../articles/fpga/plan.md)
- [Teaching assets](../assets) · [Slide 57 chart](./assets/illustrative-throughput.svg) · [Throughput PNG](../assets/fpga-inference-progression-v2.png) · [Editable throughput SVG](../assets/fpga-inference-progression.svg)
- [KV260 board connections](../assets/kv260-board-connections.png) · [KV260 request flow](../assets/kv260-request-flow.png) · [KV260 product photo via DigiKey](https://media.digikey.com/Photos/Xilinx%20Photos/MFG_SK-KV260-G.jpg)

<details>
<summary>Extra KV260 memory details for questions</summary>

- **FPGA fabric.** 648 KiB block RAM (144 blocks), 2.25 MiB UltraRAM (64 blocks), and up to about 450 KiB distributed RAM. The 234,240 logic-block flip-flops hold one bit each. The bitstream sets routing and LUT modes and can initialise LUT contents. In RAM mode, the circuit can rewrite the storage in eligible LUTs. [AMD FPGA specs](https://docs.amd.com/r/en-US/ds987-k26-som/Programmable-Logic) · [AMD LUT guide](https://docs.amd.com/r/en-US/ug574-ultrascale-clb/CLB-Overview) · [AMD configuration guide](https://docs.amd.com/r/en-US/ug909-vivado-partial-reconfiguration/Configuration-Frames)
- **Boot and storage.** 64 MB QSPI boot flash, 8 KiB module ID EEPROM and removable microSD. Storage capacity depends on the inserted card. The secure boot processor has 128 KiB ROM and 32 KiB RAM. [KV260 data sheet](https://docs.amd.com/r/en-US/ds986-kv260-starter-kit/Product-Details) · [K26 data sheet](https://docs.amd.com/r/en-US/ds987-k26-som/Functional-Overview-and-Block-Diagram) · [AMD secure boot reference](https://docs.amd.com/r/en-US/ug1085-zynq-ultrascale-trm/Secure-Processor-Block)
- **Arm memory.** 256 KiB on-chip RAM. Each Arm core has 32 KiB of L1 instruction cache and 32 KiB of L1 data cache. The Cortex-A53 cores share 1 MiB of L2 cache. Each Cortex-R5F has 128 KiB of tightly coupled RAM. [AMD processor overview](https://docs.amd.com/api/khub/documents/sbPbXcMUiRSJ2O5STvuGNQ/content)

</details>

**Talk metadata:** 12 November 2026 · Working delivery notes · Software engineers and salespeople · Follows [Lecture 3: transistor fabrication](../lecture-3/script.md).

## Questions that may come up

1. Both a CPU and an FPGA are programmable. What changes when you program each one?
2. How can the same look-up table act as an AND gate one moment and an OR gate the next?
3. What does SRAM stand for? What happens to the FPGA’s settings when you turn the power off?
4. If the look-up table already has memory, what does the flip-flop next to it remember?
5. When you reconfigure an FPGA, what happens to the wires inside it?
6. What jobs do block RAM and DSP blocks do in our design?
7. Why does the KV260 have an Arm CPU as well as an FPGA? What does each one do when we generate text?
8. If the FPGA can do many calculations in parallel, why does our model still generate one token at a time?
9. When would you choose an FPGA over a GPU or a custom chip?
10. Which version of the model actually ran on the board, and what would we measure to tell whether a new version is better?
