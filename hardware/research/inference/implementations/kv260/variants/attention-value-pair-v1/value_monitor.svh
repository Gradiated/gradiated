// Direct weighted-V phase and single-outstanding cache transaction observations.
integer vp_profile, vp_append, vp_read, vp_terms, vp_results, vp_score_ticks;
integer vp_req, vp_data, vp_mac, vp_send, vp_wait, vp_out, vp_refused, vp_delayed, vp_held;
integer vp_reads[2], vp_key[2], vp_even[2], vp_odd[2], vp_responses[2];
integer vp_start_cycle, vp_depth;
bit vp_pending, vp_value_request, vp_pair_request, vp_key_on, vp_even_on, vp_odd_on;
logic [8:0] vp_pos;
logic [5:0] vp_coord;
bit vp_read_is_pair, vp_response_is_pair, vp_key_enable, vp_even_enable, vp_odd_enable;
logic signed [15:0] vp_v_second;

`ifdef PAIRED_VALUES
assign vp_read_is_pair=dut.core.cache_read_pair;
assign vp_response_is_pair=dut.core.cache_output_pair;
assign vp_v_second=dut.core.cache_v_second;
assign vp_key_enable=dut.core.front.cache.key_read_enable;
assign vp_even_enable=dut.core.front.cache.even_read_enable;
assign vp_odd_enable=dut.core.front.cache.odd_read_enable;
`else
assign vp_read_is_pair=0;
assign vp_response_is_pair=0;
assign vp_v_second=0;
assign vp_key_enable=dut.core.cache_read_valid && dut.core.cache_read_ready;
assign vp_even_enable=vp_key_enable && !dut.core.cache_read_coordinate[0];
assign vp_odd_enable=vp_key_enable && dut.core.cache_read_coordinate[0];
`endif

initial begin
    vp_profile=$fopen("value-profile.txt","w");
    vp_append=$fopen("value-cache-appends.txt","w");
    vp_read=$fopen("value-cache-responses.txt","w");
    vp_terms=$fopen("value-terms.txt","w");
    vp_results=$fopen("value-results.txt","w");
    vp_score_ticks=$fopen("scored-steps.txt","w");
    if (vp_profile==0 || vp_append==0 || vp_read==0 || vp_terms==0 || vp_results==0 || vp_score_ticks==0)
        $fatal(1,"Cannot open value mixing replay artifacts");
end

always @(posedge aclk) if (aresetn && observing) begin
    if(dut.selected_valid && dut.core_token_ready) begin
        vp_start_cycle=int'($time/10);
        vp_depth++;
    end
    if(dut.core_logit_valid && dut.selected_ready && dut.core_logit_index==319)
        $fwrite(vp_score_ticks,"%0d %0d\n",vp_depth,int'($time/10)-vp_start_cycle+1);
    if(dut.core.front.cache.write_valid && dut.core.front.cache.write_ready)
        $fwrite(vp_append,"%0d %0d %0d %0d\n",dut.core.front.cache.write_position,
                dut.core.front.cache.write_coordinate,dut.core.front.cache.write_k,dut.core.front.cache.write_v);
    if(int'(dut.core_phase)==8) begin
        bit value_path;
        value_path=dut.core.att.state==dut.core.att.CONTEXT_REQ || dut.core.att.state==dut.core.att.CONTEXT_MAC;
        case (dut.core.att.state)
            dut.core.att.CONTEXT_REQ: vp_req++;
            dut.core.att.CONTEXT_DATA: begin
                vp_data++;
                if(!dut.core.cache_output_valid) vp_delayed++;
            end
            dut.core.att.CONTEXT_MAC: vp_mac++;
            dut.core.att.CONTEXT_SEND: vp_send++;
            dut.core.att.CONTEXT_WAIT: vp_wait++;
            dut.core.att.OUTPUT: begin
                vp_out++;
                if(!dut.core.att.result_ready) vp_held++;
            end
            default: ;
        endcase
        if(value_path && dut.core.cache_read_valid && !dut.core.cache_read_ready) vp_refused++;
        if(dut.core.cache_output_valid && dut.core.cache_output_ready) begin
            if(!vp_pending || dut.core.cache_output_position!=vp_pos[7:0] ||
               dut.core.cache_output_coordinate!=vp_coord[4:0] || vp_response_is_pair!=vp_pair_request)
                $fatal(1,"Unexpected cache response order, address or lane tag");
            vp_pending=0;
            vp_responses[vp_value_request]++;
            $fwrite(vp_read,"%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d\n",vp_depth,
                    vp_value_request,vp_pos,vp_coord,vp_pair_request,dut.core.cache_k,dut.core.cache_v,
                    vp_v_second,vp_key_on,vp_even_on,vp_odd_on);
        end
        if(dut.core.cache_read_valid && dut.core.cache_read_ready) begin
            if(vp_pending || (dut.core.cache_output_valid && dut.core.cache_output_ready))
                $fatal(1,"More than one outstanding cache transaction");
            vp_pending=1;
            vp_value_request=value_path;
            vp_pair_request=vp_read_is_pair;
            vp_pos=dut.core.cache_read_position;
            vp_coord=dut.core.cache_read_coordinate;
            vp_key_on=vp_key_enable;
            vp_even_on=vp_even_enable;
            vp_odd_on=vp_odd_enable;
            vp_reads[value_path]++;
            if(vp_key_enable) vp_key[value_path]++;
            if(vp_even_enable) vp_even[value_path]++;
            if(vp_odd_enable) vp_odd[value_path]++;
        end else if(vp_key_enable || vp_even_enable || vp_odd_enable)
            $fatal(1,"Unsolicited bank read");
        if(dut.core.att.step_valid && dut.core.att.step_mode) begin
            $fwrite(vp_terms,"%0d %0d %0d %0d %0d %0d %0d %0d\n",vp_depth,dut.core.att.step_head,
                    dut.core.att.step_coordinate,dut.core.att.step_position,dut.core.att.step_input,
                    dut.core.att.step_weight,dut.core.att.step_product,dut.core.att.step_sum);
`ifdef PAIRED_VALUES
            if(!dut.core.att.step_pair_valid || dut.core.att.step_coordinate[0])
                $fatal(1,"Weighted value pair lost lane alignment");
            $fwrite(vp_terms,"%0d %0d %0d %0d %0d %0d %0d %0d\n",vp_depth,dut.core.att.step_head,
                    int'(dut.core.att.step_coordinate)+1,dut.core.att.step_position,dut.core.att.step_input,
                    dut.core.att.step_pair_weight,dut.core.att.step_pair_product,dut.core.att.step_pair_sum);
`endif
        end
        if(dut.core.att.result_valid && dut.core.att.result_ready) begin
            if(dut.core.att.error) $fatal(1,"Unexpected attention error");
            $fwrite(vp_results,"%0d %0d %0d %0d\n",vp_depth,dut.core.att.result_index,
                    dut.core.att.result,dut.core.att.saturated);
            if(dut.core.att.result_index==5'd31) begin
                $fwrite(vp_profile,"%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",vp_depth,
                        vp_req,vp_data,vp_mac,vp_send,vp_wait,vp_out,vp_refused,vp_delayed,vp_held);
                for(int phase=0;phase<2;phase++) begin
                    $fwrite(vp_profile," %0d %0d %0d %0d %0d",vp_reads[phase],vp_responses[phase],
                            vp_key[phase],vp_even[phase],vp_odd[phase]);
                    vp_reads[phase]=0;
                    vp_responses[phase]=0;
                    vp_key[phase]=0;
                    vp_even[phase]=0;
                    vp_odd[phase]=0;
                end
                $fwrite(vp_profile,"\n");
                vp_req=0;vp_data=0;vp_mac=0;vp_send=0;vp_wait=0;vp_out=0;vp_refused=0;vp_delayed=0;vp_held=0;
            end
        end
    end
end

final begin
    if(vp_pending || vp_req || vp_mac) $fatal(1,"Incomplete attention-value trace");
    $fclose(vp_profile);$fclose(vp_append);$fclose(vp_read);
    $fclose(vp_terms);$fclose(vp_results);$fclose(vp_score_ticks);
end
