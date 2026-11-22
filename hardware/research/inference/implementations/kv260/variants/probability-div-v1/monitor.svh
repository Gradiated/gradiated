// Measure the probability phase at every occupied context depth.
integer probability_profile, divider_values, cache_addresses;
integer probability_reads, probability_launches, probability_waits, divider_steps, attention_waits;

initial begin
    probability_profile = $fopen("probability-profile.txt", "w");
    divider_values = $fopen("divider-values.txt", "w");
    cache_addresses = $fopen("cache-addresses.bin", "wb");
    if (!probability_profile || !divider_values || !cache_addresses)
        $fatal(1, "Cannot open probability replay traces");
end

always @(posedge aclk) if (aresetn && observing && int'(dut.core_phase)==8) begin
    attention_waits++;
    if (dut.core.att.cache_read_valid && dut.core.att.cache_read_ready)
        $fwrite(cache_addresses,"%c%c%c",dut.core.att.cache_read_position[8],
                dut.core.att.cache_read_position[7:0],dut.core.att.cache_read_coordinate);
    if (dut.core.att.state==dut.core.att.PROB_READ) probability_reads++;
    if (dut.core.att.state==dut.core.att.PROB_SEND &&
        dut.core.att.scalar_cmd_valid && dut.core.att.scalar_cmd_ready) probability_launches++;
    if (dut.core.att.state==dut.core.att.PROB_WAIT) begin
        probability_waits++;
        if (dut.core.att.scalar.state==dut.core.att.scalar.DIV_STEP) divider_steps++;
        if (dut.core.att.scalar.state==dut.core.att.scalar.DIV_FINISH)
            $fwrite(divider_values,"%0d %0d %0d %0d %0d %0d %0d\n",
                    dut.core.att.length,dut.core.att.head,dut.core.att.position,
                    dut.core.att.scalar_a,dut.core.att.scalar_b,
                    dut.core.att.scalar.quotient,dut.core.att.scalar.remainder);
    end
    if (dut.core.att.result_valid && dut.core.att.result_ready && dut.core.att.result_index==5'd31) begin
        $fwrite(probability_profile,"%0d %0d %0d %0d %0d %0d\n",dut.core.att.length,
                probability_reads,probability_launches,probability_waits,divider_steps,attention_waits);
        probability_reads=0;
        probability_launches=0;
        probability_waits=0;
        divider_steps=0;
        attention_waits=0;
    end
end

final begin
    if (probability_reads || probability_launches || probability_waits || divider_steps || attention_waits)
        $fatal(1, "Incomplete probability capture");
    $fclose(probability_profile);
    $fclose(divider_values);
    $fclose(cache_addresses);
end
